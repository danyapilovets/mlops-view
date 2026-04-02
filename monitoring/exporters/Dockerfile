FROM python:3.12-slim

RUN useradd --system --uid 65532 --no-create-home --shell /usr/sbin/nologin exporter \
    && pip install --no-cache-dir prometheus-client==0.21.1 requests==2.32.3

WORKDIR /app
COPY ml_metrics_exporter.py /app/ml_metrics_exporter.py

USER 65532
EXPOSE 9101

ENTRYPOINT ["python", "-u", "/app/ml_metrics_exporter.py"]
