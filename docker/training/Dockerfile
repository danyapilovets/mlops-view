# Image: us-central1-docker.pkg.dev/${GCP_PROJECT_ID}/mlops-docker/training
# syntax=docker/dockerfile:1

FROM nvidia/cuda:12.4.1-devel-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-dev \
    python3-venv \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt .

RUN pip install --extra-index-url https://download.pytorch.org/whl/cu124 -r requirements.txt

# -----------------------------------------------------------------------------
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

RUN groupadd --gid 1000 trainer && \
    useradd --uid 1000 --gid trainer --shell /bin/bash --create-home trainer

WORKDIR /app

COPY --chown=trainer:trainer scripts/ ./scripts/

USER trainer

CMD ["python3", "scripts/train.py", "--help"]
