"""Tests for the latency percentile math and the p95 budget (AIA-706, AC2)."""

from __future__ import annotations

import pytest

from app.perf.latency import LatencyBudget, percentile


def test_percentile_of_empty_input_is_zero() -> None:
    assert percentile((), 95) == 0.0


def test_percentile_of_single_sample_is_that_sample() -> None:
    assert percentile((0.42,), 95) == 0.42


def test_percentile_uses_nearest_rank_without_interpolation() -> None:
    samples = tuple(float(n) for n in range(1, 21))  # 1.0 .. 20.0

    # nearest-rank p95 of 20 samples is rank ceil(0.95 * 20) = 19 -> the 19th sample.
    assert percentile(samples, 95) == 19.0
    assert percentile(samples, 90) == 18.0


def test_percentile_endpoints_are_min_and_max() -> None:
    samples = (5.0, 1.0, 9.0, 3.0)

    assert percentile(samples, 0) == 1.0
    assert percentile(samples, 100) == 9.0


def test_percentile_is_order_independent() -> None:
    assert percentile((0.3, 0.1, 0.2), 50) == percentile((0.2, 0.3, 0.1), 50)


def test_percentile_rejects_out_of_range_q() -> None:
    with pytest.raises(ValueError):
        percentile((1.0, 2.0), 101)
    with pytest.raises(ValueError):
        percentile((1.0, 2.0), -1)


def test_budget_allows_p95_at_or_under_the_ceiling() -> None:
    budget = LatencyBudget(p95_seconds=0.20)

    assert budget.allows(0.10) is True
    assert budget.allows(0.20) is True
    assert budget.allows(0.21) is False


def test_a_zero_budget_disables_the_check() -> None:
    assert LatencyBudget(p95_seconds=0).allows(9_999.0) is True
