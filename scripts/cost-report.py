#!/usr/bin/env python3
"""GPU-oriented cost report from Prometheus (DCGM framebuffer utilization + optional $/GPU-hour estimate).

Default Prometheus URL matches in-cluster kube-prometheus-stack Service DNS:
  kube-prometheus-stack-prometheus.monitoring:9090

DCGM metrics align with NVIDIA DCGM exporter and the DAG in pipelines/dags/cost_report_dag.py:
  framebuffer util = DCGM_FI_DEV_FB_USED / (DCGM_FI_DEV_FB_USED + DCGM_FI_DEV_FB_FREE)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests

DEFAULT_PROMETHEUS = "http://kube-prometheus-stack-prometheus.monitoring:9090"

# Instant vector: per-GPU framebuffer utilization in [0, 1]
DCGM_FB_UTIL_PROMQL = "DCGM_FI_DEV_FB_USED / (DCGM_FI_DEV_FB_USED + DCGM_FI_DEV_FB_FREE)"

# Optional: count of GPUs seen by DCGM (for capacity context)
DCGM_GPU_COUNT_PROMQL = "count(DCGM_FI_DEV_FB_USED)"


def _query_instant(base_url: str, query: str, timeout: float) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v1/query"
    response = requests.get(url, params={"query": query}, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    if body.get("status") != "success":
        raise RuntimeError(f"Prometheus error: {body}")
    return body


def _results(data: dict[str, Any]) -> list[dict[str, Any]]:
    return list(data.get("data", {}).get("result", []))


def _mean_fb_util(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    values: list[float] = []
    for row in rows:
        val = row.get("value")
        if not val or len(val) < 2:
            continue
        try:
            values.append(float(val[1]))
        except (TypeError, ValueError):
            continue
    if not values:
        return None
    return sum(values) / len(values)


def build_report(
    base_url: str,
    gpu_hourly_cost_usd: float,
    horizon_hours: float,
    timeout: float,
) -> dict[str, Any]:
    fb_body = _query_instant(base_url, DCGM_FB_UTIL_PROMQL, timeout)
    fb_rows = _results(fb_body)
    mean_util = _mean_fb_util(fb_rows)

    count_body = _query_instant(base_url, DCGM_GPU_COUNT_PROMQL, timeout)
    count_rows = _results(count_body)
    gpu_count: float | None = None
    if count_rows and count_rows[0].get("value"):
        try:
            gpu_count = float(count_rows[0]["value"][1])
        except (TypeError, ValueError, KeyError):
            gpu_count = None

    # Rough bound: assume GPUs run the full horizon at mean framebuffer util as proxy for "busy fraction"
    estimated_usd: float | None = None
    if mean_util is not None and gpu_count is not None and gpu_hourly_cost_usd > 0:
        estimated_usd = gpu_count * gpu_hourly_cost_usd * horizon_hours * mean_util

    return {
        "prometheus_url": base_url,
        "horizon_hours": horizon_hours,
        "gpu_hourly_cost_usd": gpu_hourly_cost_usd,
        "queries": {
            "dcgm_fb_utilization": DCGM_FB_UTIL_PROMQL,
            "dcgm_gpu_count": DCGM_GPU_COUNT_PROMQL,
        },
        "series_count_framebuffer_util": len(fb_rows),
        "mean_framebuffer_utilization": mean_util,
        "gpu_count_dcgm": gpu_count,
        "estimated_gpu_cost_usd_for_horizon": estimated_usd,
        "formula_notes": {
            "framebuffer_util": "DCGM_FI_DEV_FB_USED / (DCGM_FI_DEV_FB_USED + DCGM_FI_DEV_FB_FREE)",
            "cost_proxy": "gpu_count * gpu_hourly_cost_usd * horizon_hours * mean_framebuffer_utilization",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="GPU cost report from Prometheus (DCGM).")
    parser.add_argument(
        "--prometheus-url",
        default=os.environ.get("PROMETHEUS_URL", DEFAULT_PROMETHEUS),
        help="Prometheus base URL (default: in-cluster kube-prometheus-stack or $PROMETHEUS_URL)",
    )
    parser.add_argument(
        "--gpu-hourly-cost-usd",
        type=float,
        default=float(
            os.environ.get(
                "GPU_USD_PER_HOUR",
                os.environ.get("GPU_HOURLY_COST_USD", "2.50"),
            )
        ),
        help="Blended $/GPU-hour ($GPU_USD_PER_HOUR or $GPU_HOURLY_COST_USD, default 2.50)",
    )
    parser.add_argument(
        "--horizon-hours",
        type=float,
        default=float(os.environ.get("REPORT_HORIZON_HOURS", "168")),
        help="Time window in hours for cost proxy (default 168 = 1 week)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("QUERY_TIMEOUT", "60")),
        help="HTTP timeout seconds ($QUERY_TIMEOUT, default 60)",
    )
    args = parser.parse_args()

    try:
        report = build_report(
            args.prometheus_url,
            args.gpu_hourly_cost_usd,
            args.horizon_hours,
            args.timeout,
        )
    except requests.RequestException as exc:
        print(json.dumps({"error": str(exc), "prometheus_url": args.prometheus_url}), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
