"""Ensure every DAG module under pipelines/dags imports without syntax or import errors."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_dag_folder_exists(dag_folder: Path) -> None:
    assert dag_folder.is_dir(), f"Missing DAG folder: {dag_folder}"


def test_all_dag_modules_import(dag_folder: Path) -> None:
    py_files = sorted(p for p in dag_folder.glob("*.py") if p.name != "__init__.py" and not p.name.startswith("."))
    assert py_files, f"No DAG Python files under {dag_folder}"

    for _path in py_files:
        mod_name = f"pipelines.dags.{_path.stem}"
        sys.modules.pop(mod_name, None)
        importlib.import_module(mod_name)
