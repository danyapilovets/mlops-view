"""End-to-end LLM fine-tuning: validate data, train, evaluate, register, notify.

``scripts/evaluate.py`` must upload eval metrics JSON to GCS at the object path
from env ``EVAL_METRICS_GCS_OBJECT`` (templated), including a numeric ``loss``
field for ``check_evaluation``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import requests
from airflow import DAG
from airflow.models import Variable
from airflow.operators.branch import BranchPythonOperator
from airflow.operators.python import PythonOperator
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

try:
    from airflow.utils.helpers import render_template_to_string
except ImportError:  # Airflow <2.6 compatibility
    from airflow.utils.template import render_template_to_string

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


def _training_image() -> str:
    return Variable.get("training_image", default_var=TRAINING_IMAGE)


def _mlflow_uri() -> str:
    return Variable.get("mlflow_tracking_uri", default_var=MLFLOW_URI)


def _data_bucket() -> str:
    return Variable.get("data_bucket", default_var=DATA_BUCKET)


def _model_bucket() -> str:
    return Variable.get("model_bucket", default_var=MODEL_BUCKET)


def _teams_webhook_url() -> str:
    return Variable.get("teams_webhook_url", default_var="")


def _eval_loss_threshold() -> float:
    return float(Variable.get("eval_loss_threshold", default_var="0.5"))


def _dataset_gcs_prefix() -> str:
    return Variable.get("finetune_dataset_gcs_prefix", default_var="datasets/llm-finetune/")


def _k8s_namespace_training() -> str:
    return Variable.get("k8s_namespace_ml_training", default_var="ml-training")


def _kubernetes_conn_id() -> str:
    return Variable.get("kubernetes_conn_id", default_var="kubernetes_default")


def _eval_metrics_object_template() -> str:
    return Variable.get(
        "finetune_eval_metrics_object_template",
        default_var="airflow/{{ dag_run.run_id }}/eval_metrics.json",
    )


def validate_dataset(**context: Any) -> None:
    from google.cloud import storage

    bucket_name = _data_bucket()
    prefix = _dataset_gcs_prefix()
    client = storage.Client()
    blobs = list(client.list_blobs(bucket_name, prefix=prefix, max_results=1))
    if not blobs:
        raise FileNotFoundError(
            f"No objects under gs://{bucket_name}/{prefix} (check data_bucket / dataset prefix)"
        )
    logger.info("Dataset prefix validated: gs://%s/%s", bucket_name, prefix)


def register_model(**context: Any) -> None:
    import os

    import mlflow
    from mlflow.tracking import MlflowClient

    os.environ["MLFLOW_TRACKING_URI"] = _mlflow_uri()
    ti = context["ti"]
    metrics = ti.xcom_pull(key="eval_metrics", task_ids="fetch_eval_metrics") or {}
    exp = Variable.get("mlflow_experiment_finetune", default_var="llm-finetune")
    mclient = MlflowClient()
    if mclient.get_experiment_by_name(exp) is None:
        mclient.create_experiment(exp)
    mlflow.set_experiment(exp)
    model_name = Variable.get("mlflow_model_name", default_var="llm-finetuned")
    source_uri = Variable.get("finetune_mlflow_model_source_uri", default_var="").strip()
    with mlflow.start_run(run_name=context["dag_run"].run_id):
        for key, val in metrics.items():
            if isinstance(val, (int, float)):
                mlflow.log_metric(str(key), float(val))
        if source_uri:
            mlflow.register_model(source_uri, model_name)
        else:
            logger.info(
                "Skipping mlflow.register_model (set Airflow Variable finetune_mlflow_model_source_uri)"
            )


def _post_teams(title: str, text: str) -> None:
    url = _teams_webhook_url().strip()
    if not url:
        logger.warning("teams_webhook_url empty; skipping Teams notification")
        return
    payload: dict[str, Any] = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": title,
        "themeColor": "0078D4",
        "sections": [{"activityTitle": title, "text": text}],
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()


def notify_success(**context: Any) -> None:
    run_id = context["dag_run"].run_id
    _post_teams(
        "LLM fine-tune succeeded",
        f"DAG **llm_finetune** run `{run_id}` completed successfully.",
    )


def notify_failure(**context: Any) -> None:
    run_id = context["dag_run"].run_id
    _post_teams(
        "LLM fine-tune failed evaluation",
        f"DAG **llm_finetune** run `{run_id}` did not pass loss threshold.",
    )


def fetch_eval_metrics_from_gcs(**context: Any) -> dict[str, Any]:
    from google.cloud import storage

    bucket = _data_bucket()
    tmpl = _eval_metrics_object_template()
    object_name = render_template_to_string(tmpl, context)
    client = storage.Client()
    blob = client.bucket(bucket).blob(object_name)
    if not blob.exists():
        raise FileNotFoundError(f"Missing eval metrics: gs://{bucket}/{object_name}")
    data = json.loads(blob.download_as_text())
    context["ti"].xcom_push(key="eval_metrics", value=data)
    return data


def choose_after_eval(**context: Any) -> str:
    ti = context["ti"]
    metrics = ti.xcom_pull(key="eval_metrics", task_ids="fetch_eval_metrics") or {}
    loss = float(metrics.get("loss", 999.0))
    threshold = _eval_loss_threshold()
    if loss <= threshold:
        return "register_model"
    return "notify_failure"


default_args = {
    "owner": "ml-platform",
    "depends_on_past": False,
    "retries": 1,
}

with DAG(
    dag_id="llm_finetune",
    default_args=default_args,
    description="LLM fine-tuning: validate, GPU train, evaluate, MLflow register, Teams notify",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ml-platform", "llm", "training", "gpu"],
    render_template_as_native_obj=True,
) as dag:
    mlflow_uri = _mlflow_uri()
    data_bucket = _data_bucket()
    model_bucket = _model_bucket()

    validate = PythonOperator(
        task_id="validate_dataset",
        python_callable=validate_dataset,
    )

    gpu_toleration = k8s.V1Toleration(
        key="nvidia.com/gpu",
        operator="Equal",
        value="training",
        effect="NoSchedule",
    )
    node_affinity = k8s.V1Affinity(
        node_affinity=k8s.V1NodeAffinity(
            required_during_scheduling_ignored_during_execution=k8s.V1NodeSelector(
                node_selector_terms=[
                    k8s.V1NodeSelectorTerm(
                        match_expressions=[
                            k8s.V1NodeSelectorRequirement(
                                key="node_pool",
                                operator="In",
                                values=["gpu-training"],
                            )
                        ]
                    )
                ]
            )
        )
    )
    train_resources = k8s.V1ResourceRequirements(
        requests={"nvidia.com/gpu": "1", "cpu": "4", "memory": "16Gi"},
        limits={"nvidia.com/gpu": "1", "cpu": "8", "memory": "32Gi"},
    )

    train_model = KubernetesPodOperator(
        task_id="train_model",
        name="llm-train-{{ ts_nodash }}",
        namespace=_k8s_namespace_training(),
        image=_training_image(),
        cmds=["python", "scripts/train.py"],
        env_vars=[
            k8s.V1EnvVar(name="MLFLOW_TRACKING_URI", value=mlflow_uri),
            k8s.V1EnvVar(name="GCS_DATA_BUCKET", value=data_bucket),
            k8s.V1EnvVar(name="GCS_MODEL_BUCKET", value=model_bucket),
            k8s.V1EnvVar(name="AIRFLOW_RUN_ID", value="{{ dag_run.run_id }}"),
        ],
        container_resources=train_resources,
        tolerations=[gpu_toleration],
        affinity=node_affinity,
        kubernetes_conn_id=_kubernetes_conn_id(),
        get_logs=True,
        is_delete_operator_pod=True,
    )

    evaluate_model = KubernetesPodOperator(
        task_id="evaluate_model",
        name="llm-eval-{{ ts_nodash }}",
        namespace=_k8s_namespace_training(),
        image=_training_image(),
        cmds=["python", "scripts/evaluate.py"],
        env_vars=[
            k8s.V1EnvVar(name="MLFLOW_TRACKING_URI", value=mlflow_uri),
            k8s.V1EnvVar(name="GCS_DATA_BUCKET", value=data_bucket),
            k8s.V1EnvVar(name="GCS_MODEL_BUCKET", value=model_bucket),
            k8s.V1EnvVar(name="EVAL_METRICS_GCS_OBJECT", value=_eval_metrics_object_template()),
            k8s.V1EnvVar(name="AIRFLOW_RUN_ID", value="{{ dag_run.run_id }}"),
        ],
        container_resources=k8s.V1ResourceRequirements(
            requests={"cpu": "2", "memory": "8Gi"},
            limits={"cpu": "4", "memory": "16Gi"},
        ),
        tolerations=[gpu_toleration],
        affinity=node_affinity,
        kubernetes_conn_id=_kubernetes_conn_id(),
        get_logs=True,
        is_delete_operator_pod=True,
    )

    fetch_eval_metrics = PythonOperator(
        task_id="fetch_eval_metrics",
        python_callable=fetch_eval_metrics_from_gcs,
    )

    check_evaluation = BranchPythonOperator(
        task_id="check_evaluation",
        python_callable=choose_after_eval,
    )

    register = PythonOperator(
        task_id="register_model",
        python_callable=register_model,
    )

    notify_ok = PythonOperator(
        task_id="notify_success",
        python_callable=notify_success,
    )

    notify_bad = PythonOperator(
        task_id="notify_failure",
        python_callable=notify_failure,
    )

    validate >> train_model >> evaluate_model >> fetch_eval_metrics >> check_evaluation
    check_evaluation >> register >> notify_ok
    check_evaluation >> notify_bad
