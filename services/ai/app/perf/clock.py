"""A deterministic monotonic clock for measuring latency in tests and harnesses (AIA-706).

Real wall-clock timing makes latency assertions flaky and slow. :class:`ManualClock` stands in for
``time.monotonic``: reads return the current value and never go backwards, and a collaborator (a
latency-injecting fake provider) advances it by a known amount to model the cost of a call. A
harness that reads the clock before and after a request therefore gets an exact, reproducible
latency, with a cache hit -- which does no provider work -- advancing nothing and so measuring zero.
"""

from __future__ import annotations


class ManualClock:
    """A monotonic clock whose value only moves when :meth:`advance` is called."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = float(start)

    def __call__(self) -> float:
        """Read the current monotonic value, in seconds."""
        return self._now

    def advance(self, seconds: float) -> None:
        """Move the clock forward by ``seconds`` (never backwards)."""
        if seconds < 0:
            raise ValueError("a monotonic clock cannot move backwards")
        self._now += seconds
