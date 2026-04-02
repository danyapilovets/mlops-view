#!/usr/bin/env bash
# Fetch GKE credentials, install Flux CLI if missing, bootstrap the GitOps GitHub repository.
set -o errexit
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

GCP_PROJECT="${GCP_PROJECT:-${GCP_PROJECT_ID:-}}"
: "${GCP_PROJECT:?Set GCP_PROJECT or GCP_PROJECT_ID (e.g. export GCP_PROJECT_ID=mlops-platform-dev)}"
: "${GITHUB_TOKEN:?Set GITHUB_TOKEN for flux bootstrap github}"
: "${FLUX_OWNER:?Set FLUX_OWNER (GitHub org or user)}"
: "${FLUX_REPO:?Set FLUX_REPO (repository name, without org)}"

export GITHUB_TOKEN

GKE_CLUSTER_NAME="${GKE_CLUSTER_NAME:-mlops-platform-dev-gke}"
GCP_REGION="${GCP_REGION:-us-central1}"
FLUX_PATH="${FLUX_PATH:-clusters/dev}"
FLUX_BRANCH="${FLUX_BRANCH:-main}"
CLUSTER_ENV="${CLUSTER_ENV:-dev}"

info() { echo "INFO  - $*"; }
error() { echo "ERROR - $*" >&2; exit 1; }

command -v gcloud >/dev/null 2>&1 || error "gcloud not found"
command -v kubectl >/dev/null 2>&1 || error "kubectl not found"

info "Fetching credentials for ${GKE_CLUSTER_NAME} (${GCP_REGION}, project ${GCP_PROJECT})"
gcloud container clusters get-credentials "${GKE_CLUSTER_NAME}" \
  --region "${GCP_REGION}" \
  --project "${GCP_PROJECT}"

if ! command -v flux >/dev/null 2>&1; then
  info "Installing flux CLI to ~/.local/bin"
  mkdir -p "${HOME}/.local/bin"
  export PATH="${HOME}/.local/bin:${PATH}"
  curl -fsSL https://fluxcd.io/install.sh | bash -s --
fi

info "flux bootstrap github --owner=${FLUX_OWNER} --repository=${FLUX_REPO} --path=${FLUX_PATH}"
flux bootstrap github \
  --owner="${FLUX_OWNER}" \
  --repository="${FLUX_REPO}" \
  --branch="${FLUX_BRANCH}" \
  --path="${FLUX_PATH}" \
  --network-policy=false

CLUSTER_VARS="${REPO_ROOT}/clusters/${CLUSTER_ENV}/cluster-vars.yaml"
if [[ -f "${CLUSTER_VARS}" ]]; then
  info "kubectl apply -f ${CLUSTER_VARS}"
  kubectl apply -f "${CLUSTER_VARS}"
fi

info "kubectl apply -f ${REPO_ROOT}/clusters/base/namespaces.yaml"
kubectl apply -f "${REPO_ROOT}/clusters/base/namespaces.yaml"

info "Bootstrap complete."
