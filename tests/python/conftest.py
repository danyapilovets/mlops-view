"""Shared pytest fixtures and lightweight stubs so DAG modules import without full Airflow/Kubernetes installs."""

from __future__ import annotations

import os
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_EXPORTER_DIR = REPO_ROOT / "monitoring" / "exporters"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(_EXPORTER_DIR) not in sys.path:
    sys.path.insert(0, str(_EXPORTER_DIR))


def _install_airflow_and_kubernetes_stubs() -> None:
    if "airflow" in sys.modules and getattr(sys.modules.get("kubernetes.client.models"), "__getattr__", None):
        return

    def _dummy_class(name: str) -> type:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        return type(name, (), {"__init__": __init__})

    models = types.ModuleType("models")

    def models_getattr(name: str) -> type:
        return _dummy_class(name)

    models.__getattr__ = models_getattr  # type: ignore[attr-defined]

    k8s_client = types.ModuleType("kubernetes.client")
    k8s_client.models = models

    k8s_pkg = types.ModuleType("kubernetes")
    k8s_pkg.client = k8s_client

    sys.modules.setdefault("kubernetes", k8s_pkg)
    sys.modules.setdefault("kubernetes.client", k8s_client)
    sys.modules.setdefault("kubernetes.client.models", models)

    class _DAG:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> _DAG:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    class _Variable:
        @staticmethod
        def get(key: str, default_var: Any = None) -> Any:
            return default_var

    class _BaseOperator:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def __rshift__(self, other: Any) -> Any:
            return other

    class PythonOperator(_BaseOperator):
        pass

    class BranchPythonOperator(_BaseOperator):
        pass

    class KubernetesPodOperator(_BaseOperator):
        pass

    airflow_pkg = types.ModuleType("airflow")
    airflow_pkg.DAG = _DAG

    airflow_models = types.ModuleType("airflow.models")
    airflow_models.Variable = _Variable

    airflow_ops_python = types.ModuleType("airflow.operators.python")
    airflow_ops_python.PythonOperator = PythonOperator

    airflow_ops_branch = types.ModuleType("airflow.operators.branch")
    airflow_ops_branch.BranchPythonOperator = BranchPythonOperator

    airflow_prov_pod = types.ModuleType("airflow.providers.cncf.kubernetes.operators.pod")
    airflow_prov_pod.KubernetesPodOperator = KubernetesPodOperator

    def render_template_to_string(template: str, context: Any) -> str:
        return template

    airflow_utils_helpers = types.ModuleType("airflow.utils.helpers")
    airflow_utils_helpers.render_template_to_string = render_template_to_string

    airflow_utils_template = types.ModuleType("airflow.utils.template")
    airflow_utils_template.render_template_to_string = render_template_to_string

    sys.modules.setdefault("airflow", airflow_pkg)
    sys.modules.setdefault("airflow.models", airflow_models)
    sys.modules.setdefault("airflow.operators", types.ModuleType("airflow.operators"))
    sys.modules.setdefault("airflow.operators.python", airflow_ops_python)
    sys.modules.setdefault("airflow.operators.branch", airflow_ops_branch)
    sys.modules.setdefault("airflow.providers", types.ModuleType("airflow.providers"))
    sys.modules.setdefault("airflow.providers.cncf", types.ModuleType("airflow.providers.cncf"))
    sys.modules.setdefault("airflow.providers.cncf.kubernetes", types.ModuleType("airflow.providers.cncf.kubernetes"))
    sys.modules.setdefault(
        "airflow.providers.cncf.kubernetes.operators",
        types.ModuleType("airflow.providers.cncf.kubernetes.operators"),
    )
    sys.modules.setdefault("airflow.providers.cncf.kubernetes.operators.pod", airflow_prov_pod)
    sys.modules.setdefault("airflow.utils", types.ModuleType("airflow.utils"))
    sys.modules.setdefault("airflow.utils.helpers", airflow_utils_helpers)
    sys.modules.setdefault("airflow.utils.template", airflow_utils_template)


_install_airflow_and_kubernetes_stubs()


@pytest.fixture(scope="session", autouse=True)
def _airflow_unit_test_env() -> None:
    os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
    os.environ.setdefault("AIRFLOW__CORE__UNIT_TEST_MODE", "True")


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def dag_folder() -> Path:
    return REPO_ROOT / "pipelines" / "dags"


@pytest.fixture
def sample_vllm_metrics_text() -> str:
    """OpenMetrics text compatible with prometheus_client parsing of vLLM counters."""
    return (
        "# TYPE vllm:prompt_tokens_total counter\n"
        "vllm:prompt_tokens_total 100\n"
        "# TYPE vllm:generation_tokens_total counter\n"
        "vllm:generation_tokens_total 50\n"
        "# TYPE vllm:e2e_request_latency_seconds_sum counter\n"
        "vllm:e2e_request_latency_seconds_sum 12.5\n"
        "# TYPE vllm:e2e_request_latency_seconds_count counter\n"
        "vllm:e2e_request_latency_seconds_count 25\n"
    )


@pytest.fixture
def reset_exporter_globals() -> Iterator[None]:
    from monitoring.exporters import ml_metrics_exporter as exp

    prev = (exp._prev_prompt, exp._prev_generation, exp._prev_ts)
    exp._prev_prompt = None
    exp._prev_generation = None
    exp._prev_ts = None
    yield
    exp._prev_prompt, exp._prev_generation, exp._prev_ts = prev
