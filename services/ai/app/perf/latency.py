"""Latency percentiles and the p95 budget they are checked against (AIA-706, AC2).

A latency budget is a tail guarantee, so it is stated as a percentile, not a mean: a few slow calls
should not be hidden by many fast ones. :func:`percentile` uses the nearest-rank method (no
interpolation) so the result is always an observed sample and is trivial to reason about in a test.
:class:`LatencyBudget` is the ceiling the harness checks the measured p95 against; a budget of ``0``
disables the check, keeping the guarantee opt-in like the token budgets it sits beside.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


def percentile(samples: Sequence[float], q: float) -> float:
    """Return the nearest-rank ``q``-th percentile of ``samples`` (``q`` in ``[0, 100]``).

    An empty input yields ``0.0``. ``q = 0`` returns the minimum and ``q = 100`` the maximum.
    """
    if not 0 <= q <= 100:
        raise ValueError("q must be between 0 and 100")
    if not samples:
        return 0.0
    ordered = sorted(samples)
    if q == 0:
        return ordered[0]
    rank = math.ceil(q / 100 * len(ordered))
    return ordered[rank - 1]


@dataclass(frozen=True, slots=True)
class LatencyBudget:
    """A p95 latency ceiling in seconds; ``0`` disables the check (always allows)."""

    p95_seconds: float

    def allows(self, p95: float) -> bool:
        """Whether a measured p95 latency is within budget."""
        return self.p95_seconds <= 0 or p95 <= self.p95_seconds
