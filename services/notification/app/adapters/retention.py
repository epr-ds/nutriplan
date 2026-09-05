"""The retention policy both store adapters enforce (AC2).

The feed is a rolling window over recent history, bounded two independent ways:

* **By age** -- nothing older than ``ttl_seconds`` is readable. Records carry a Redis
  ``EX`` so they expire on their own, and the per-user indexes are swept by score, because a
  sorted-set *member* cannot carry its own TTL.
* **By count** -- a user's index keeps at most ``max_entries`` ids. Age alone is not enough:
  a very busy account could accumulate an unbounded sorted set well inside the window, and
  that set is read on every feed query.

Holding the policy in one value object (rather than inline in each adapter) is what lets the
in-memory and Redis stores be checked against the same expectations -- if only one of them
pruned, the contract suite would pass and production would drift.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """How long notifications live and how many of them a single user's index keeps."""

    ttl_seconds: int = 2_592_000
    max_entries: int = 500

    @property
    def expires(self) -> bool:
        """False when ``ttl_seconds`` is non-positive, meaning "keep until evicted"."""
        return self.ttl_seconds > 0

    @property
    def bounded(self) -> bool:
        """False when ``max_entries`` is non-positive, meaning "no length cap"."""
        return self.max_entries > 0

    def horizon(self, now: float) -> float:
        """The oldest creation time still inside the window at ``now`` (epoch seconds)."""
        return now - self.ttl_seconds

    def is_expired(self, created_at: float, *, now: float) -> bool:
        """True when a record created at ``created_at`` has aged out by ``now``."""
        return self.expires and created_at <= self.horizon(now)
