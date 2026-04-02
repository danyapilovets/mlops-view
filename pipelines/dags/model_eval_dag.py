"""Scheduled model evaluation, benchmark, and MLflow promotion.

`scripts/benchmark.py` (pipeline-runner image) must write Airflow XCom JSON to
``/airflow/xcom/return.json`` when this DAG uses ``do_xcom_push=True`` (e.g.
``{"latency_ms": 42.0, "throughput_rps": 120.0}``).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

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


def _pipeline_runner_image() -> str:
    return Variable.get("pipeline_runner_image", default_var=PIPELINE_RUNNER_IMAGE)


def _mlflow_uri() -> str:
    return Variable.get("mlflow_tracking_uri", default_var=MLFLOW_URI)


def _model_bucket() -> str:
    return Variable.get("model_bucket", default_var=MODEL_BUCKET)


def _data_bucket() -> str:
    return Variable.get("data_bucket", default_var=DATA_BUCKET)


def _k8s_namespace_pipelines() -> str:
    return Variable.get("k8s_namespace_ml_platform", default_var="ml-platform")


def _kubernetes_conn_id() -> str:
    return Variable.get("kubernetes_conn_id", default_var="kubernetes_default")


def _registered_model_name() -> str:
    return Variable.get("mlflow_registered_model_name", default_var="llm-finetuned")


def _baseline_latency_ms() -> float:
    return float(Variable.get("model_eval_baseline_latency_ms", default_var="100.0"))


def _baseline_throughput_rps() -> float:
    return float(Variable.get("model_eval_baseline_throughput_rps", default_var="50.0"))


def load_latest_model(**context: Any) -> dict[str, Any]:
    import os

    from mlflow.tracking import MlflowClient

    os.environ["MLFLOW_TRACKING_URI"] = _mlflow_uri()
    client = MlflowClient()
    name = _registered_model_name()
    try:
        versions = client.search_model_versions(filter_string=f"name='{name}'")
    except TypeError:
        versions = client.search_model_versions(f"name='{name}'")
    if not versions:
        raise ValueError(f"No model versions found for registered model '{name}'")
    latest = max(versions, key=lambda v: int(v.version))
    info = {
        "name": latest.name,
        "version": latest.version,
        "source": latest.source,
        "run_id": latest.run_id,
    }
    context["ti"].xcom_push(key="latest_model", value=info)
    logger.info("Latest model: %s v%s", info["name"], info["version"])
    return info


def compare_with_baseline(**context: Any) -> dict[str, Any]:
    ti = context["ti"]
    raw = ti.xcom_pull(key="return_value", task_ids="run_benchmark")
    if isinstance(raw, str):
        try:
            metrics = json.loads(raw)
        except json.JSONDecodeError:
            metrics = {"latency_ms": float("inf"), "throughput_rps": 0.0}
    elif isinstance(raw, dict):
        metrics = raw
    else:
        metrics = {"latency_ms": float("inf"), "throughput_rps": 0.0}

    latency = float(metrics.get("latency_ms", metrics.get("p99_latency_ms", float("inf"))))
    throughput = float(metrics.get("throughput_rps", metrics.get("rps", 0.0)))
    baseline_lat = _baseline_latency_ms()
    baseline_tput = _baseline_throughput_rps()
    better = (latency <= baseline_lat) and (throughput >= baseline_tput)
    result = {
        "latency_ms": latency,
        "throughput_rps": throughput,
        "baseline_latency_ms": baseline_lat,
        "baseline_throughput_rps": baseline_tput,
        "promote": better,
    }
    context["ti"].xcom_push(key="compare_result", value=result)
    logger.info("Benchmark compare: %s", result)
    return result


def promote_model(**context: Any) -> None:
    import os

    from mlflow.tracking import MlflowClient

    ti = context["ti"]
    compare = ti.xcom_pull(key="compare_result", task_ids="compare_with_baseline") or {}
    if not compare.get("promote"):
        logger.info("Promotion skipped: metrics did not beat baseline")
        return

    os.environ["MLFLOW_TRACKING_URI"] = _mlflow_uri()
    latest = ti.xcom_pull(key="latest_model", task_ids="load_latest_model") or {}
    version = str(latest.get("version", ""))
    name = latest.get("name") or _registered_model_name()
    if not version:
        raise ValueError("Missing model version for promotion")

    client = MlflowClient()
    client.transition_model_version_stage(
        name=name,
        version=version,
        stage="Production",
        archive_existing_versions=False,
    )
    logger.info("Promoted %s v%s to Production", name, version)


default_args = {
    "owner": "ml-platform",
    "depends_on_past": False,
    "retries": 1,
}

with DAG(
    dag_id="model_eval",
    default_args=default_args,
    description="Daily benchmark of latest MLflow model and conditional promotion",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ml-platform", "evaluation", "mlflow", "benchmark"],
    render_template_as_native_obj=True,
) as dag:
    mlflow_uri = _mlflow_uri()
    model_bucket = _model_bucket()
    data_bucket = _data_bucket()

    load_latest = PythonOperator(
        task_id="load_latest_model",
        python_callable=load_latest_model,
    )

    run_benchmark_pod = KubernetesPodOperator(
        task_id="run_benchmark",
        name="model-benchmark-{{ ts_nodash }}",
        namespace=_k8s_namespace_pipelines(),
        image=_pipeline_runner_image(),
        cmds=["python", "scripts/benchmark.py"],
        env_vars=[
            k8s.V1EnvVar(name="MLFLOW_TRACKING_URI", value=mlflow_uri),
            k8s.V1EnvVar(name="GCS_MODEL_BUCKET", value=model_bucket),
            k8s.V1EnvVar(name="GCS_DATA_BUCKET", value=data_bucket),
            k8s.V1EnvVar(
                name="MLFLOW_MODEL_INFO_JSON",
                value="{{ ti.xcom_pull(task_ids='load_latest_model', key='latest_model') | tojson }}",
            ),
        ],
        container_resources=k8s.V1ResourceRequirements(
            requests={"cpu": "2", "memory": "4Gi"},
            limits={"cpu": "4", "memory": "8Gi"},
        ),
        kubernetes_conn_id=_kubernetes_conn_id(),
        get_logs=True,
        is_delete_operator_pod=True,
        do_xcom_push=True,
    )

    compare = PythonOperator(
        task_id="compare_with_baseline",
        python_callable=compare_with_baseline,
    )

    promote = PythonOperator(
        task_id="promote_model",
        python_callable=promote_model,
    )

    load_latest >> run_benchmark_pod >> compare >> promote
