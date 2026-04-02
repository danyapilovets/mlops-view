"""Minimal CI smoke tests (repository structure and import sanity)."""

from __future__ import annotations

from pathlib import Path


def test_repo_root_has_helm_charts() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "helm" / "llm-serving" / "Chart.yaml").is_file()
    assert (root / "helm" / "ml-gateway" / "Chart.yaml").is_file()
    assert (root / "helm" / "grafana-dashboards" / "Chart.yaml").is_file()
