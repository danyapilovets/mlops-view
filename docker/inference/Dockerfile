# Image: us-central1-docker.pkg.dev/${GCP_PROJECT_ID}/mlops-docker/inference
# syntax=docker/dockerfile:1

FROM vllm/vllm-openai:v0.5.4

USER root

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface

# hadolint ignore=DL3013
RUN pip install --no-cache-dir \
    prometheus-client \
    google-cloud-storage \
    huggingface_hub

WORKDIR /app

COPY scripts/ /app/scripts/

RUN chmod +x /app/scripts/entrypoint.sh && \
    groupadd --gid 1000 vllm && \
    useradd --uid 1000 --gid vllm --shell /bin/bash --create-home --home-dir /app vllm && \
    mkdir -p /app/.cache/huggingface /models/weights && \
    chown -R vllm:vllm /app /models

USER vllm

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
