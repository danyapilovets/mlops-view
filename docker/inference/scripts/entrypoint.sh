#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${MODEL_SOURCE:-}" ]]; then
  OUT="${MODEL_DOWNLOAD_PATH:-/models/weights}"
  python3 /app/scripts/download_model.py --source "${MODEL_SOURCE}" --output-dir "${OUT}"
  if [[ -z "${MODEL_NAME:-}" ]]; then
    export MODEL_NAME="${OUT}"
  fi
fi

if [[ -z "${MODEL_NAME:-}" ]]; then
  echo "error: MODEL_NAME is required (or set MODEL_SOURCE to download first)" >&2
  exit 1
fi

TP="${TENSOR_PARALLEL_SIZE:-1}"
MAX_LEN="${MAX_MODEL_LEN:-4096}"

exec vllm serve "${MODEL_NAME}" \
  --tensor-parallel-size "${TP}" \
  --max-model-len "${MAX_LEN}" \
  "$@"
