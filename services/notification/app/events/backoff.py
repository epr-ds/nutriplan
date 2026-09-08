"""How long a failed delivery waits before it is served again (NTF-204, AC1).

NTF-201 gave failures a retry *budget* but not a retry *schedule*: every pending message was
reclaimed on the same flat 60-second cadence, however many times it had already failed. That
is wrong in both directions at once. A handler failing because a dependency is down is retried
at full rate against a dependency that is down, and every message stranded by one outage comes
back in the same sweep the moment it clears -- a thundering herd aimed at the service least
able to absorb it, at the exact moment it is least able to. Meanwhile a genuinely poisonous
message burns its whole budget in five minutes and is parked long before anyone can deploy the
fix that would have let it through.

So the wait grows with the attempt count: each failure buys the next one more room.

**The base is the reclaim idle window, and it cannot be shorter.** The obvious backoff starts
at a second or two, and this one cannot, because of what a reclaim actually is. This service
does not retry a message it holds -- it *takes back* a message left pending, and from the
pending list alone there is no way to distinguish "the handler raised and nobody is working on
this" from "another replica is still working on this right now". The only evidence available is
how long the entry has sat idle, so the idle floor that keeps a reclaim from stealing live work
(``NOTIFICATION_EVENT_RECLAIM_IDLE_MS``) is also the soonest any retry can safely happen.
Backoff extends that floor; it never undercuts it. A retry that fired in two seconds would
manufacture exactly the duplicate NTF-103 then has to suppress.

**Jitter is derived from the delivery id, not from a random number.** Two consumers sweeping
the same pending list must agree on whether an entry is due. With a random roll, one replica
would decide "due" and claim it while the other decided "not yet" -- so the spread would be
decided by whichever replica swept first, which is no spread at all. Hashing the delivery id
gives every entry a stable offset that every replica computes identically, and different
entries different offsets, which is the whole point.

Jitter only ever moves a retry *earlier* than its nominal slot, never later. Spreading upward
would let the cap be exceeded and would make the worst-case time-to-park unpredictable; an
operator watching a poison message needs to know it will be in the dead-letter queue within a
bounded time, not a bounded time plus however much jitter happened to be rolled.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

DEFAULT_MULTIPLIER = 2.0
"""Each attempt waits twice as long as the last.

Doubling rather than the more aggressive factors used for API clients: the budget is only five
attempts, and at a 60s base a multiplier of 4 would put the last retry 64 minutes out, which is
long past the point where a notification about an order is still worth sending.
"""

DEFAULT_CAP_MS = 3_600_000
"""An hour. No single wait exceeds this however many attempts have been burned."""

DEFAULT_JITTER = 0.2
"""Spread each due time over the last 20% of its window. See the module docstring."""

_HASH_SPACE = 1 << 32
"""The slice of the digest used to derive an entry's offset, as an integer."""


@dataclass(frozen=True, slots=True)
class RetrySchedule:
    """The growing wait between one failed delivery and the next attempt at it.

    Immutable and free of I/O so the worker, both consumer adapters and the tests all reason
    about due-ness with the same object rather than three approximations of one rule.
    """

    base_ms: int
    """The first wait, and the floor under every later one. See the module docstring."""

    multiplier: float = DEFAULT_MULTIPLIER
    cap_ms: int = DEFAULT_CAP_MS
    jitter: float = DEFAULT_JITTER

    def __post_init__(self) -> None:
        # Clamped rather than rejected: these arrive from environment variables, and a worker
        # that refuses to start because someone set a multiplier of 0.5 has turned a harmless
        # typo into an outage of the consumer. Every value below degrades to "no backoff",
        # which is the behaviour NTF-201 already had.
        object.__setattr__(self, "base_ms", max(0, int(self.base_ms)))
        object.__setattr__(self, "multiplier", max(1.0, float(self.multiplier)))
        object.__setattr__(self, "cap_ms", max(self.base_ms, int(self.cap_ms)))
        object.__setattr__(self, "jitter", min(1.0, max(0.0, float(self.jitter))))

    @property
    def floor_ms(self) -> int:
        """The shortest wait any entry can have -- what a pre-filter may safely ask for.

        A consumer asks the broker for entries idle at least this long *before* applying the
        per-entry rule, so the overwhelming majority of not-yet-due entries are excluded by
        the broker rather than fetched and discarded. It is the base reduced by the maximum
        jitter, because an entry on its first attempt with an unlucky hash is due exactly
        then, and a pre-filter that asked for the full base would never return it.
        """
        return int(self.base_ms * (1.0 - self.jitter))

    def delay_for(self, attempt: int, *, delivery_id: str = "") -> int:
        """How long, in ms, a delivery on its ``attempt``-th try must sit idle before retry.

        ``attempt`` is the number of times the broker has already delivered the message, so
        the first wait is ``base_ms`` and the *n*-th is ``base_ms * multiplier**(n-1)``,
        capped. ``delivery_id`` selects the entry's stable jitter offset; omitting it gives
        the nominal, un-jittered schedule, which is what makes the tests legible.
        """
        exponent = max(0, int(attempt) - 1)
        nominal = min(float(self.cap_ms), self.base_ms * (self.multiplier**exponent))
        return int(nominal * (1.0 - self.jitter * _offset(delivery_id)))

    def is_due(self, *, attempt: int, idle_ms: int, delivery_id: str = "") -> bool:
        """True when a delivery has waited long enough to be tried again."""
        return idle_ms >= self.delay_for(attempt, delivery_id=delivery_id)


def _offset(delivery_id: str) -> float:
    """Map a delivery id onto a stable fraction in ``[0, 1)``.

    ``blake2b`` rather than :func:`hash`: Python's string hash is randomised per process by
    default, so two replicas -- or the same pod after a restart -- would disagree about an
    entry's offset, which is precisely the disagreement this function exists to remove.
    """
    if not delivery_id:
        return 0.0
    digest = hashlib.blake2b(delivery_id.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") / _HASH_SPACE
