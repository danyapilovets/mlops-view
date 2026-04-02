"""Weekly GPU utilization and cost report from Prometheus, uploaded to GCS."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)

# --- Naming contract defaults (override via Airflow Variables) ---
TRAINING_IMAGE = "us-central1-docker.pkg.dev/mlops-platform-dev/mlops-docker/training:latest"
PIPELINE_RUNNER_IMAGE = (
    "us-central1-docker.pkg.dev/mlops-platform-dev/mlops-docker/pipeline-runner:latest"
)
MLFLOW_URI = "http://mlflow.ml-platform:5000"
PROMETHEUS_URL = "http://kube-prometheus-stack-prometheus.monitoring:9090"
MODEL_BUCKET = "mlops-platform-dev-models"
DATA_BUCKET = "mlops-platform-dev-data"

# Per-GPU framebuffer utilization (DCGM): used / (used + free)
GPU_FB_UTIL_JOIN_PROMQL = """
(
  DCGM_FI_DEV_FB_USED
  / (DCGM_FI_DEV_FB_USED + DCGM_FI_DEV_FB_FREE)
)
* on(kubernetes_node) group_left(label_node_pool)
label_replace(
  kube_node_labels,
  "kubernetes_node",
  "$1",
  "node",
  "(.+)"
)
""".strip()

DCGM_FB_PROMQL = """
DCGM_FI_DEV_FB_USED
/ (DCGM_FI_DEV_FB_USED + DCGM_FI_DEV_FB_FREE)
""".strip()

KUBE_NODE_LABELS_PROMQL = "kube_node_labels"


def _prometheus_url() -> str:
    return Variable.get("prometheus_url", default_var=PROMETHEUS_URL)


def _data_bucket() -> str:
    return Variable.get("data_bucket", default_var=DATA_BUCKET)


def _gpu_hourly_cost_usd() -> float:
    return float(Variable.get("gpu_hourly_cost_usd", default_var="2.50"))


def _report_gcs_prefix() -> str:
    return Variable.get("cost_report_gcs_prefix", default_var="reports/gpu-cost/")


def _prometheus_query_path() -> str:
    return Variable.get("prometheus_query_path", default_var="/api/v1/query")


def _prometheus_query_range_path() -> str:
    return Variable.get("prometheus_query_range_path", default_var="/api/v1/query_range")


def _query_prometheus(url: str, params: dict[str, Any]) -> dict[str, Any]:
    r = requests.get(url, params=params, timeout=120)
    r.raise_for_status()
    body = r.json()
    if body.get("status") != "success":
        raise RuntimeError(f"Prometheus error: {body}")
    return body


def _instant_vector_result(data: dict[str, Any]) -> list[dict[str, Any]]:
    return list(data.get("data", {}).get("result", []))


def _join_dcgm_with_node_labels(
    dcgm_rows: list[dict[str, Any]],
    label_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Join DCGM series (kubernetes_node) with kube_node_labels (node) in Python."""
    labels_by_node: dict[str, dict[str, str]] = {}
    for row in label_rows:
        m = row.get("metric", {})
        node = m.get("node") or m.get("kubernetes_node") or m.get("Hostname")
        if not node:
            continue
        labels_by_node[node] = {k: v for k, v in m.items() if k.startswith("label_")}

    out: list[dict[str, Any]] = []
    for row in dcgm_rows:
        m = row.get("metric", {})
        kn = m.get("kubernetes_node") or m.get("node") or m.get("Hostname")
        if not kn:
            continue
        pool = None
        if kn in labels_by_node:
            pool = labels_by_node[kn].get("label_node_pool")
        merged = dict(m)
        if pool is not None:
            merged["label_node_pool"] = pool
        out.append({"metric": merged, "value": row.get("value")})
    return out


def collect_gpu_metrics(**context: Any) -> dict[str, Any]:
    base = _prometheus_url().rstrip("/")
    query_url = f"{base}{_prometheus_query_path()}"
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)

    join_body = _query_prometheus(
        query_url,
        {"query": GPU_FB_UTIL_JOIN_PROMQL, "time": str(end.timestamp())},
    )
    series = _instant_vector_result(join_body)

    if not series:
        logger.warning("Join query returned no series; falling back to DCGM + kube_node_labels merge")
        dcgm_body = _query_prometheus(
            query_url,
            {"query": DCGM_FB_PROMQL, "time": str(end.timestamp())},
        )
        lbl_body = _query_prometheus(
            query_url,
            {"query": KUBE_NODE_LABELS_PROMQL, "time": str(end.timestamp())},
        )
        series = _join_dcgm_with_node_labels(
            _instant_vector_result(dcgm_body),
            _instant_vector_result(lbl_body),
        )

    range_url = f"{base}{_prometheus_query_range_path()}"
    range_body = _query_prometheus(
        range_url,
        {
            "query": DCGM_FB_PROMQL,
            "start": str(start.timestamp()),
            "end": str(end.timestamp()),
            "step": "3600",
        },
    )
    range_result = range_body.get("data", {}).get("result", [])

    payload = {
        "window_start_utc": start.isoformat(),
        "window_end_utc": end.isoformat(),
        "gpu_fb_utilization_instant": series,
        "dcgm_fb_utilization_range": range_result,
    }
    context["ti"].xcom_push(key="gpu_metrics", value=payload)
    return payload


def generate_cost_report(**context: Any) -> dict[str, Any]:
    ti = context["ti"]
    raw = ti.xcom_pull(key="gpu_metrics", task_ids="collect_gpu_metrics") or {}
    hourly = _gpu_hourly_cost_usd()
    rows = raw.get("gpu_fb_utilization_instant") or []
    line_items: list[dict[str, Any]] = []
    total_gpu_hours_equivalent = 0.0

    for row in rows:
        metric = row.get("metric", {})
        pool = metric.get("label_node_pool", "unknown")
        try:
            util = float(row.get("value", [None, "0"])[1])
        except (TypeError, ValueError, IndexError):
            util = 0.0
        gpu_hours = util * 24.0 * 7.0
        total_gpu_hours_equivalent += gpu_hours
        line_items.append(
            {
                "node_pool_label": pool,
                "kubernetes_node": metric.get(
                    "kubernetes_node", metric.get("node", metric.get("Hostname", ""))
                ),
                "gpu_uuid": metric.get("UUID", metric.get("gpu", "")),
                "framebuffer_utilization_ratio": util,
                "estimated_gpu_hours_week": gpu_hours,
                "estimated_cost_usd": gpu_hours * hourly,
            }
        )

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "gpu_hourly_cost_usd": hourly,
        "line_items": line_items,
        "total_estimated_gpu_hours_week": total_gpu_hours_equivalent,
        "total_estimated_cost_usd": total_gpu_hours_equivalent * hourly,
        "source_metrics_note": (
            "GPU memory ratio uses DCGM_FI_DEV_FB_USED / (DCGM_FI_DEV_FB_USED + DCGM_FI_DEV_FB_FREE); "
            "node_pool from kube_node_labels via kubernetes_node/node join (not DCGM node_pool label)."
        ),
    }
    context["ti"].xcom_push(key="cost_report", value=report)
    return report


def upload_report(**context: Any) -> str:
    from google.cloud import storage

    ti = context["ti"]
    report = ti.xcom_pull(key="cost_report", task_ids="generate_cost_report") or {}
    bucket_name = _data_bucket()
    prefix = _report_gcs_prefix().strip("/")
    key = f"{prefix}/gpu-cost-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(key)
    blob.upload_from_string(
        json.dumps(report, indent=2),
        content_type="application/json",
    )
    uri = f"gs://{bucket_name}/{key}"
    logger.info("Uploaded cost report to %s", uri)
    return uri


default_args = {
    "owner": "ml-platform",
    "depends_on_past": False,
    "retries": 1,
}

with DAG(
    dag_id="cost_report",
    default_args=default_args,
    description="Weekly GPU cost report from Prometheus DCGM + kube_node_labels",
    schedule="@weekly",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ml-platform", "cost", "gpu", "prometheus"],
    render_template_as_native_obj=True,
) as dag:
    collect = PythonOperator(
        task_id="collect_gpu_metrics",
        python_callable=collect_gpu_metrics,
    )
    generate = PythonOperator(
        task_id="generate_cost_report",
        python_callable=generate_cost_report,
    )
    upload = PythonOperator(
        task_id="upload_report",
        python_callable=upload_report,
    )

    collect >> generate >> upload
