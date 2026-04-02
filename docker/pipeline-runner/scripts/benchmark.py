#!/usr/bin/env python3
"""Benchmark a vLLM OpenAI-compatible HTTP endpoint: latency percentiles and throughput."""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urljoin

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="vLLM OpenAI-compatible endpoint benchmark")
    p.add_argument(
        "--endpoint",
        required=True,
        help="Base URL (e.g. http://vllm:8000) or full chat-completions URL",
    )
    p.add_argument("--num-requests", type=int, default=100, help="Total requests to send")
    p.add_argument("--concurrency", type=int, default=4, help="Concurrent workers")
    p.add_argument(
        "--model",
        default="default",
        help="Model name in JSON body (OpenAI API field 'model')",
    )
    p.add_argument("--max-tokens", type=int, default=32)
    p.add_argument("--timeout", type=float, default=120.0, help="Per-request timeout seconds")
    return p.parse_args()


def _chat_url(base: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/v1/chat/completions"):
        return base
    return urljoin(base + "/", "v1/chat/completions")


def _one_request(
    url: str,
    model: str,
    max_tokens: int,
    timeout: float,
) -> tuple[float, bool, str | None]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
        "max_tokens": max_tokens,
    }
    headers = {"Content-Type": "application/json"}
    t0 = time.perf_counter()
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=timeout)
        dt = time.perf_counter() - t0
        if r.status_code >= 400:
            return dt, False, f"HTTP {r.status_code}: {r.text[:200]}"
        return dt, True, None
    except requests.RequestException as e:
        dt = time.perf_counter() - t0
        return dt, False, str(e)


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def main() -> int:
    args = parse_args()
    if args.num_requests < 1:
        logger.error("--num-requests must be >= 1")
        return 1
    if args.concurrency < 1:
        logger.error("--concurrency must be >= 1")
        return 1

    url = _chat_url(args.endpoint)
    logger.info("Benchmarking %s (%d requests, concurrency=%d)", url, args.num_requests, args.concurrency)

    latencies: list[float] = []
    errors: list[str] = []
    wall_t0 = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = [
            ex.submit(_one_request, url, args.model, args.max_tokens, args.timeout) for _ in range(args.num_requests)
        ]
        for fut in as_completed(futures):
            dt, ok, err = fut.result()
            if ok:
                latencies.append(dt)
            elif err:
                errors.append(err)

    wall_dt = time.perf_counter() - wall_t0
    ok_count = len(latencies)
    err_count = len(errors)

    latencies.sort()
    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    p99 = _percentile(latencies, 99)
    throughput = ok_count / wall_dt if wall_dt > 0 else 0.0

    result: dict[str, Any] = {
        "endpoint": url,
        "num_requests": args.num_requests,
        "concurrency": args.concurrency,
        "successful_requests": ok_count,
        "failed_requests": err_count,
        "wall_time_seconds": round(wall_dt, 6),
        "throughput_rps": round(throughput, 4),
        "latency_seconds": {
            "p50": round(p50, 6) if latencies else None,
            "p95": round(p95, 6) if latencies else None,
            "p99": round(p99, 6) if latencies else None,
            "mean": round(statistics.mean(latencies), 6) if latencies else None,
        },
        "errors_sample": errors[:5],
    }

    print(json.dumps(result, indent=2))
    if err_count and ok_count == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
