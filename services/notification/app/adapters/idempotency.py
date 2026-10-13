"""The idempotency window both dedupe adapters enforce (AC2).

Two durations, for two different failure modes:

* ``ttl_seconds`` -- how long a handled event is remembered. This bounds *replay*: an event
  redelivered inside the window is a no-op, one arriving after it is treated as new. Long
  enough to cover the bus's realistic redelivery horizon (retries, a consumer restart, a
  dead-letter replay from NTF-204), short enough that the keys do not accumulate forever.
* ``provisional_seconds`` -- how long the *unconfirmed* claim taken before the notification
  is written survives. This bounds *loss*: it is the only window in which a hard-killed
  worker can suppress a notification it never actually delivered. Long enough to cover a
  slow store write, short enough that a redelivery moments later still gets through.

Keeping them in one value object means the store adapters cannot disagree about either
bound, the same way :class:`~app.adapters.retention.RetentionPolicy` keeps the feed's window
in one place.

The window is deliberately shorter than the feed's retention (30 days by default). If it
were longer, a replay could be suppressed on behalf of an original that had already aged out
of the feed -- the user would see neither the first notification nor its replacement.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IdempotencyWindow:
    """How long a handled event is remembered, and how long an unconfirmed claim lives."""

    ttl_seconds: int = 86_400
    provisional_seconds: int = 60

    @property
    def enabled(self) -> bool:
        """False when ``ttl_seconds`` is non-positive, which turns deduplication off.

        Every claim then succeeds. That is a legitimate setting for a throwaway environment
        replaying a fixture stream on purpose, and it is why the flag lives here rather than
        being an ``if`` scattered through each adapter.
        """
        return self.ttl_seconds > 0

    @property
    def provisional(self) -> int:
        """The initial lease length, never longer than the window it will be extended to."""
        return max(1, min(self.provisional_seconds, self.ttl_seconds))
