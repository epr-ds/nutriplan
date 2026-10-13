"""The idempotency window's arithmetic and its two switches (AC2)."""

from __future__ import annotations

import pytest

from app.adapters.idempotency import IdempotencyWindow


def test_the_defaults_are_a_day_and_a_minute() -> None:
    window = IdempotencyWindow()

    assert window.ttl_seconds == 24 * 60 * 60
    assert window.provisional == 60
    assert window.enabled


def test_a_non_positive_ttl_disables_deduplication() -> None:
    assert not IdempotencyWindow(ttl_seconds=0).enabled
    assert not IdempotencyWindow(ttl_seconds=-1).enabled


@pytest.mark.parametrize("provisional", [0, -5])
def test_the_provisional_lease_is_never_shorter_than_a_second(provisional: int) -> None:
    """A zero-second lease would expire before the write it is meant to protect."""
    assert IdempotencyWindow(ttl_seconds=600, provisional_seconds=provisional).provisional == 1


def test_the_provisional_lease_never_exceeds_the_window_it_extends_to() -> None:
    """Confirming must lengthen a lease, never shorten it.

    If the provisional lease outlived the full window, a confirmed claim would expire
    *sooner* than an abandoned one -- a replay would then get through precisely because the
    first delivery succeeded.
    """
    window = IdempotencyWindow(ttl_seconds=30, provisional_seconds=300)

    assert window.provisional == 30


def test_the_window_is_frozen_and_comparable() -> None:
    assert IdempotencyWindow(ttl_seconds=10) == IdempotencyWindow(ttl_seconds=10)
    assert IdempotencyWindow(ttl_seconds=10) != IdempotencyWindow(ttl_seconds=11)
