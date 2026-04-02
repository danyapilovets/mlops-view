#!/usr/bin/env bash
# GitOps validation (pattern inspired by Playtika cloud-orchestration/scripts/validate.sh):
# - kustomize build clusters/dev|staging|prod → kubeconform (-strict)
# - helm lint + helm template on all charts under helm/
# - YAML syntax (repo YAML, skipping caches and Helm template trees)
# Succeeds only if every step passes (exit 0).
set -o errexit
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

info() { echo "INFO  - $*"; }
error() { echo "ERROR - $*" >&2; exit 1; }

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x "${REPO_ROOT}/.venv/bin/python3" ]]; then
  PYTHON_BIN="${REPO_ROOT}/.venv/bin/python3"
fi

# Prefer standalone kustomize; fall back to kubectl's embedded implementation.
KUSTOMIZE_LABEL=""
if command -v kustomize >/dev/null 2>&1; then
  KUSTOMIZE_LABEL="kustomize"
elif command -v kubectl >/dev/null 2>&1; then
  KUSTOMIZE_LABEL="kubectl kustomize"
else
  error "Neither kustomize nor kubectl found in PATH"
fi

command -v kubeconform >/dev/null 2>&1 || error "kubeconform not found in PATH"
command -v helm >/dev/null 2>&1 || error "helm not found in PATH"

KUSTOMIZE_OPTS=( --load-restrictor=LoadRestrictionsNone )
KUBECONFORM_OPTS=( -strict -ignore-missing-schemas -summary )

kustomize_build() {
  local dir="$1"
  if [[ "${KUSTOMIZE_LABEL}" == "kubectl kustomize" ]]; then
    kubectl kustomize "${KUSTOMIZE_OPTS[@]}" "${dir}"
  else
    kustomize build "${KUSTOMIZE_OPTS[@]}" "${dir}"
  fi
}

validate_kustomize_clusters() {
  local env
  for env in dev staging prod; do
    info "${KUSTOMIZE_LABEL} clusters/${env} | kubeconform -strict"
    kustomize_build "clusters/${env}" | kubeconform "${KUBECONFORM_OPTS[@]}" -
  done
}

helm_lint_all() {
  local chart_dir chart_yaml
  while IFS= read -r -d '' chart_yaml; do
    chart_dir="$(dirname "${chart_yaml}")"
    info "helm lint ${chart_dir}"
    helm lint "${chart_dir}"
  done < <(find "${REPO_ROOT}/helm" -maxdepth 3 -name Chart.yaml -print0)
}

helm_template_all() {
  local chart_dir chart_yaml values
  while IFS= read -r -d '' chart_yaml; do
    chart_dir="$(dirname "${chart_yaml}")"
    values=""
    case "$(basename "${chart_dir}")" in
      llm-serving) values="${chart_dir}/values-dev.yaml" ;;
      *) values="${chart_dir}/values.yaml" ;;
    esac
    if [[ ! -f "${values}" ]]; then
      info "helm template ${chart_dir} (default values only)"
      helm template validate-release "${chart_dir}" >/dev/null
    else
      info "helm template ${chart_dir} -f ${values}"
      helm template validate-release "${chart_dir}" -f "${values}" >/dev/null
    fi
  done < <(find "${REPO_ROOT}/helm" -maxdepth 3 -name Chart.yaml -print0)
}

validate_yaml_syntax() {
  VALIDATE_REPO_ROOT="${REPO_ROOT}" "${PYTHON_BIN}" <<'PY'
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError as e:
    print("ERROR - PyYAML required: pip install pyyaml or pip install '.[dev]'", file=sys.stderr)
    raise SystemExit(1) from e

root = Path(os.environ["VALIDATE_REPO_ROOT"])
skip_parts = {".git", ".terraform", ".venv", "node_modules", ".pytest_cache", ".ruff_cache"}
suffixes = {".yaml", ".yml"}
skip_names = {"values.yaml", "kustomizeconfig.yaml"}

errors = 0
for path in root.rglob("*"):
    if not path.is_file():
        continue
    if path.suffix.lower() not in suffixes:
        continue
    if path.name in skip_names:
        continue
    try:
        rel = path.relative_to(root)
    except ValueError:
        continue
    if any(p in skip_parts for p in rel.parts):
        continue
    if "templates" in rel.parts and "helm" in rel.parts:
        continue
    try:
        text = path.read_text(encoding="utf-8")
        for _ in yaml.safe_load_all(text):
            pass
    except Exception as exc:
        print(f"YAML error {path}: {exc}", file=sys.stderr)
        errors += 1

raise SystemExit(errors)
PY
}

main() {
  validate_kustomize_clusters
  helm_lint_all
  helm_template_all
  validate_yaml_syntax
  info "All validations passed."
}

main "$@"
