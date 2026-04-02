#!/usr/bin/env python3
"""Business-oriented Prometheus exporter for vLLM inference.

Scrapes native vLLM OpenMetrics from /metrics and publishes derived gauges.
Dashboards should keep using vllm:* directly; this process adds MLOps cost and
token-velocity signals that are not redundant with raw vLLM series.
"""

from __future__ import annotations

import logging
import os
import time

import requests
from prometheus_client import Gauge, Info, start_http_server
from prometheus_client.parser import text_string_to_metric_families

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
LOG = logging.getLogger(__name__)

VLLM_METRICS_URL = os.environ.get("VLLM_METRICS_URL", "http://127.0.0.1:8000/metrics")
SCRAPE_INTERVAL = float(os.environ.get("SCRAPE_INTERVAL", "15"))
EXPORTER_PORT = int(os.environ.get("EXPORTER_PORT", "9101"))
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "10"))
GPU_COST_USD_PER_HOUR = float(os.environ.get("GPU_COST_USD_PER_HOUR", "0"))
GPUS_PER_INSTANCE = float(os.environ.get("GPUS_PER_INSTANCE", "1"))
MODEL_NAME = os.environ.get("MODEL_NAME", "unknown")
MODEL_VERSION = os.environ.get("MODEL_VERSION", "unknown")

TOKENS_PER_SECOND = Gauge(
    "mlops_inference_tokens_per_second",
    "Combined prompt+generation token throughput derived from vLLM counters.",
)
COST_PER_REQUEST = Gauge(
    "mlops_inference_cost_per_request",
    "Estimated USD cost per request from mean e2e latency and GPU hourly rate.",
)
MODEL_INFO = Info(
    "mlops_inference_model_version",
    "Deployed model identity (exported as mlops_inference_model_version_info).",
)

_prev_prompt: float | None = None
_prev_generation: float | None = None
_prev_ts: float | None = None


def _parse_vllm(text: str) -> tuple[float, float, float, float]:
    """Return (prompt_tokens_total, generation_tokens_total, e2e_sum, e2e_count)."""
    prompt_total = 0.0
    generation_total = 0.0
    e2e_sum = 0.0
    e2e_count = 0.0
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            name = sample.name
            if name == "vllm:prompt_tokens_total":
                prompt_total += float(sample.value)
            elif name == "vllm:generation_tokens_total":
                generation_total += float(sample.value)
            elif name in (
                "vllm:e2e_request_latency_seconds_sum",
                "vllm:e2e_request_latency_seconds_sum_total",
            ):
                e2e_sum += float(sample.value)
            elif name in (
                "vllm:e2e_request_latency_seconds_count",
                "vllm:e2e_request_latency_seconds_count_total",
            ):
                e2e_count += float(sample.value)
    return prompt_total, generation_total, e2e_sum, e2e_count


def _scrape_once() -> None:
    global _prev_prompt, _prev_generation, _prev_ts

    response = requests.get(VLLM_METRICS_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    now = time.time()
    prompt_total, generation_total, e2e_sum, e2e_count = _parse_vllm(response.text)

    if _prev_ts is not None and _prev_prompt is not None and _prev_generation is not None and now > _prev_ts:
        dt = now - _prev_ts
        delta_tokens = (prompt_total - _prev_prompt) + (generation_total - _prev_generation)
        if dt > 0 and delta_tokens >= 0:
            TOKENS_PER_SECOND.set(delta_tokens / dt)

    _prev_prompt = prompt_total
    _prev_generation = generation_total
    _prev_ts = now

    if e2e_count > 0 and GPU_COST_USD_PER_HOUR > 0:
        mean_e2e = e2e_sum / e2e_count
        usd_per_gpu_second = GPU_COST_USD_PER_HOUR / 3600.0
        COST_PER_REQUEST.set(mean_e2e * usd_per_gpu_second * GPUS_PER_INSTANCE)
    else:
        COST_PER_REQUEST.set(0.0)

    MODEL_INFO.info(
        {
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "vllm_metrics_url": VLLM_METRICS_URL,
        }
    )


def main() -> None:
    start_http_server(EXPORTER_PORT)
    LOG.info(
        "Exporter on :%s scraping %s every %ss (GPU_COST_USD_PER_HOUR=%s)",
        EXPORTER_PORT,
        VLLM_METRICS_URL,
        SCRAPE_INTERVAL,
        GPU_COST_USD_PER_HOUR,
    )
    while True:
        try:
            _scrape_once()
        except Exception:
            LOG.exception("Scrape failed")
        time.sleep(SCRAPE_INTERVAL)


if __name__ == "__main__":
    main()
