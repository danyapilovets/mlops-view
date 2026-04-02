#!/usr/bin/env bash
# Run helm lint on every chart under helm/ (fails CI if any chart fails).
set -o errexit
set -o pipefail
set -o nounset

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

command -v helm >/dev/null 2>&1 || {
  echo "ERROR: helm not found in PATH" >&2
  exit 1
}

failed=0
while IFS= read -r -d '' chart_yaml; do
  chart="$(dirname "${chart_yaml}")"
  rel="${chart#"${REPO_ROOT}/"}"
  echo "INFO  - helm lint ${rel}"
  if ! helm lint "${chart}"; then
    failed=1
  fi
done < <(find "${REPO_ROOT}/helm" -maxdepth 3 -mindepth 2 -name Chart.yaml -print0 2>/dev/null)

if [[ "${failed}" -ne 0 ]]; then
  echo "ERROR - one or more helm lint runs failed" >&2
  exit 1
fi

echo "INFO  - all helm lint checks passed"
