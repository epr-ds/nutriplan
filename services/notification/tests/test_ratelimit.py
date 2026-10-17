"""Unit tests for the per-user rate limiter (NTF-702)."""

from __future__ import annotations

import pytest

from app.core.ratelimit import RateLimitExceeded, check_rate_limit, reset_rate_limit


def test_it_allows_hits_up_to_the_limit() -> None:
    reset_rate_limit()

    for _ in range(3):
        check_rate_limit("u1", "/notifications", limit=3)

    with pytest.raises(RateLimitExceeded) as exc:
        check_rate_limit("u1", "/notifications", limit=3)
    assert exc.value.retry_after >= 1


def test_the_allowance_is_per_user() -> None:
    reset_rate_limit()
    check_rate_limit("u1", "/notifications", limit=1)

    check_rate_limit("u2", "/notifications", limit=1)  # different user, not blocked


def test_the_allowance_is_shared_across_the_route_family() -> None:
    reset_rate_limit()
    check_rate_limit("u1", "/notifications", limit=1)

    # The preferences endpoint lives under the same ``notifications`` family.
    with pytest.raises(RateLimitExceeded):
        check_rate_limit("u1", "/notifications/preferences", limit=1)


def test_a_non_positive_limit_disables_the_check() -> None:
    reset_rate_limit()

    for _ in range(50):
        check_rate_limit("u1", "/notifications", limit=0)


def test_the_window_lapses() -> None:
    reset_rate_limit()
    now = 1_000.0

    def clock() -> float:
        return now

    check_rate_limit("u1", "/notifications", limit=1, window_seconds=60.0, clock=clock)
    with pytest.raises(RateLimitExceeded):
        check_rate_limit("u1", "/notifications", limit=1, window_seconds=60.0, clock=clock)

    now += 61.0
    check_rate_limit("u1", "/notifications", limit=1, window_seconds=60.0, clock=clock)
