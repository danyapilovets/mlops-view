"""Tests for monitoring/exporters/ml_metrics_exporter.py (vLLM /metrics parsing)."""

from __future__ import annotations

from unittest import mock

import pytest

from monitoring.exporters import ml_metrics_exporter as exp


def test_parse_vllm_extracts_counters(sample_vllm_metrics_text: str) -> None:
    prompt_total, gen_total, e2e_sum, e2e_count = exp._parse_vllm(sample_vllm_metrics_text)
    assert prompt_total == 100.0
    assert gen_total == 50.0
    assert e2e_sum == 12.5
    assert e2e_count == 25.0


def test_parse_vllm_empty_text_returns_zeros() -> None:
    prompt_total, gen_total, e2e_sum, e2e_count = exp._parse_vllm("")
    assert prompt_total == gen_total == e2e_sum == e2e_count == 0.0


@pytest.mark.usefixtures("reset_exporter_globals")
def test_scrape_once_parses_mocked_metrics(
    sample_vllm_metrics_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(exp, "GPU_COST_USD_PER_HOUR", 3.6)
    monkeypatch.setattr(exp, "GPUS_PER_INSTANCE", 1.0)

    mock_resp = mock.Mock()
    mock_resp.text = sample_vllm_metrics_text
    mock_resp.raise_for_status = mock.Mock()

    with mock.patch.object(exp.requests, "get", return_value=mock_resp):
        with mock.patch.object(exp.time, "time", side_effect=[1000.0, 1015.0]):
            exp._scrape_once()
        with mock.patch.object(exp.time, "time", side_effect=[1015.0, 1030.0]):
            exp._scrape_once()

    assert mock_resp.raise_for_status.call_count == 2
    mean_e2e = 12.5 / 25.0
    expected_cost = mean_e2e * (3.6 / 3600.0) * 1.0
    assert exp.COST_PER_REQUEST._value.get() == pytest.approx(expected_cost, rel=1e-5)
