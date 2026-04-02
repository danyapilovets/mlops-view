# Image: us-central1-docker.pkg.dev/${GCP_PROJECT_ID}/mlops-docker/pipeline-runner
# syntax=docker/dockerfile:1

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY scripts/ ./scripts/

RUN groupadd --gid 1000 runner && \
    useradd --uid 1000 --gid runner --shell /bin/bash --create-home runner && \
    chown -R runner:runner /app

USER runner

CMD ["python", "scripts/benchmark.py", "--help"]
