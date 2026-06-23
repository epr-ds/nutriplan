"""Retry policy and backoff math, isolated so they can be unit-tested in pure form.

The schedule is exponential backoff with full jitter — the standard defense against
thundering-herd retries against a rate-limited provider. Jitter draws from an
injectable ``rand`` so tests stay deterministic.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How many times to retry a transient failure, and how long to wait between tries.

    ``max_retries`` counts retries *after* the first attempt, so the total number of
    attempts is ``max_retries + 1``.
    """

    max_retries: int = 2
    base_delay: float = 0.5
    max_delay: float = 8.0
    multiplier: float = 2.0


def compute_backoff(
    attempt: int,
    policy: RetryPolicy,
    rand: Callable[[], float] = random.random,
) -> float:
    """Delay before the retry following a given 0-based ``attempt``.

    Exponential (``base_delay * multiplier**attempt``), capped at ``max_delay``, then
    scaled by full jitter in ``[0, 1)``. With ``rand`` returning ``1.0`` the result is
    the deterministic capped ceiling, which is what the tests assert against.
    """
    ceiling = min(policy.max_delay, policy.base_delay * (policy.multiplier**attempt))
    return ceiling * rand()
