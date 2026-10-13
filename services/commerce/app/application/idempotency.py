"""The idempotency-store port (COM-209).

An ``Idempotency-Key`` lets a client safely retry ``POST /orders`` without risking a second charge
or a duplicate order: the first successful create records ``(user_id, key) -> order_id`` together
with a fingerprint of the request, and any later request carrying the same key *replays* that
original order instead of creating a new one. Keeping this behind a small port means the use case
stays persistence-agnostic (a SQL adapter backs prod/CI; an in-memory double backs unit tests).

The store deliberately records **only successful** creates, so a declined charge or a validation
error leaves no key behind and the client is free to retry. The ``request_fingerprint`` lets the
caller detect the *same key reused for a different request* — a client bug that should surface as a
``409`` rather than silently returning the wrong order.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class IdempotencyRecord:
    """A previously honoured ``Idempotency-Key`` and the order it produced.

    ``request_fingerprint`` is a stable hash of the originating request; it is compared on replay
    so the same key presented with a *different* body is rejected instead of returning a mismatched
    result.
    """

    key: str
    user_id: uuid.UUID
    order_id: uuid.UUID
    request_fingerprint: str


class IdempotencyStore(Protocol):
    """Persistence port that remembers the result of an idempotent create for a given key."""

    def find(self, key: str, *, user_id: uuid.UUID) -> IdempotencyRecord | None:
        """Return the record previously stored for ``key`` under ``user_id``, or ``None``."""
        ...

    def save(
        self, key: str, *, user_id: uuid.UUID, order_id: uuid.UUID, request_fingerprint: str
    ) -> None:
        """Record that ``key`` produced ``order_id``.

        Scoped per user and unique on ``(user_id, key)``. A concurrent request that recorded the
        same key first is not an error — the adapter absorbs the collision and leaves the original
        record in place, since that original order is the result the caller will replay.
        """
        ...
