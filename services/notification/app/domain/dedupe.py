"""The deterministic dedupe key that makes a replayed event a no-op (AC1).

One domain event can legitimately produce several notifications -- an ``order_delivered``
event may raise both a delivery notice and a "rate your order" prompt -- and the same event
can legitimately reach two different users. What must *never* happen twice is the same
event producing the same notification type for the same user. That triple is the identity
this module derives a key from.

**Determinism is the whole point.** The key has to be identical across processes, replicas,
and restarts, because the duplicate is usually being handled by a *different* consumer than
the original. That rules out Python's builtin :func:`hash`, which is randomized per process
by ``PYTHONHASHSEED``: a dedupe key built from it would agree with itself inside one worker
and silently disagree with every other worker, which looks exactly like "dedupe works on my
machine" and spams users in production. We use SHA-256 instead.

**Injectivity matters as much as determinism.** Joining the parts with a separator is not
enough: ``("order:1", "u")`` and ``("order", "1:u")`` would produce the same string, so two
unrelated events would suppress each other. Each component is therefore length-prefixed
before hashing, which makes the encoding unambiguous no matter what characters an upstream
event id happens to contain.

The key keeps the notification type as a readable prefix. Ops work on this data with
``redis-cli``, and ``…:d:order_confirmed:9f2c…`` tells you what a key is for while a bare
digest tells you nothing; the type is a bounded enum, so it cannot smuggle a separator in.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from app.domain.enums import NotificationType
from app.domain.errors import InvalidDedupeKey

DIGEST_LENGTH = 32
"""Hex characters of SHA-256 kept: 128 bits, far past any practical collision risk."""


def _digest(*parts: str) -> str:
    """Hash ``parts`` unambiguously by length-prefixing each one before feeding it in."""
    hasher = hashlib.sha256()
    for part in parts:
        raw = part.encode("utf-8")
        hasher.update(f"{len(raw)}:".encode("ascii"))
        hasher.update(raw)
    return hasher.hexdigest()[:DIGEST_LENGTH]


@dataclass(frozen=True, slots=True)
class DedupeKey:
    """The identity of "this event, for this user, as this notification type"."""

    notification_type: NotificationType
    digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.notification_type, NotificationType):
            object.__setattr__(self, "notification_type", NotificationType(self.notification_type))
        if not self.digest:
            raise InvalidDedupeKey("dedupe key digest must not be empty")

    @classmethod
    def for_event(
        cls,
        event_id: str,
        *,
        user_id: uuid.UUID | str,
        notification_type: NotificationType | str,
    ) -> DedupeKey:
        """Derive the key for one (event, user, type) triple.

        ``event_id`` is the upstream event's own identifier -- the Redis stream message id
        for NTF-202, or whatever the producer guarantees stable across a redelivery. It is
        required to be non-blank: an empty event id would collapse *every* event of that
        type for that user onto one key, so the first notification a user ever received
        would suppress all the rest. That is a silent, total outage of notifications for
        that user, so it fails loudly here instead.
        """
        notification_type = NotificationType(notification_type)
        event = event_id.strip()
        if not event:
            raise InvalidDedupeKey("event_id must not be blank")
        return cls(
            notification_type=notification_type,
            digest=_digest(event, str(user_id), notification_type.value),
        )

    def __str__(self) -> str:
        """The token used as (part of) a store key: readable type, then the digest."""
        return f"{self.notification_type.value}:{self.digest}"


@dataclass(frozen=True, slots=True)
class Claim:
    """The outcome of trying to claim a dedupe key.

    ``holder`` is the id that owns the key either way -- your own when ``acquired`` is true,
    the original owner's when it is false -- so the duplicate path can resolve what the
    first delivery produced instead of only learning that something already happened.
    """

    acquired: bool
    holder: str

    def __bool__(self) -> bool:
        """A claim is truthy when it was actually acquired."""
        return self.acquired
