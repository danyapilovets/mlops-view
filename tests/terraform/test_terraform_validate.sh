#!/usr/bin/env bash
# terraform validate (-backend=false) for the root stack and each module.
set -o errexit
set -o pipefail
set -o nounset

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TF_ROOT="${REPO_ROOT}/terraform"

command -v terraform >/dev/null 2>&1 || {
  echo "ERROR: terraform not found in PATH" >&2
  exit 1
}

validate_dir() {
  local dir="$1"
  echo "INFO  - terraform init -backend=false ( ${dir#"${REPO_ROOT}/"} )"
  (cd "${dir}" && terraform init -backend=false -input=false >/dev/null)
  echo "INFO  - terraform validate ( ${dir#"${REPO_ROOT}/"} )"
  (cd "${dir}" && terraform validate)
}

validate_dir "${TF_ROOT}"

if [[ -d "${TF_ROOT}/modules" ]]; then
  for mod in "${TF_ROOT}/modules"/*; do
    [[ -d "${mod}" ]] || continue
    [[ -n "$(find "${mod}" -maxdepth 1 -name '*.tf' -print -quit)" ]] || continue
    validate_dir "${mod}"
  done
fi

echo "INFO  - all terraform validate checks passed"
