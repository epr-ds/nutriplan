"""Record a notification at most once per (event, user, type) -- AC3.

This is the only write path event consumers should use. ``NotificationRepository.add`` is a
blunt "store this", which is correct for a store and wrong for a consumer: message buses
redeliver. Redis Streams re-serve a pending entry whenever a consumer dies mid-batch, a
deploy restarts a pod, or NTF-204 replays a dead-letter, so "handle each event exactly once"
is not something the bus can promise and has to be established here.

The sequence is claim, write, confirm:

1. **Claim** the dedupe key under a short provisional lease. Losing the claim means another
   delivery of this event already handled it, so this one stops -- the no-op the story asks
   for. The refusal names the original notification, so the caller gets *what* happened
   rather than only *that* something did.
2. **Write** the notification.
3. **Confirm** the claim, extending it to the full idempotency window.

Ordering claim-before-write is what prevents the duplicate; the provisional lease in step 1
is what stops that choice from turning a crash into a permanently swallowed notification.
Both failure directions are handled explicitly rather than left to chance:

* the write raising -- the common case, a store outage -- **releases** the claim, so the very
  next redelivery is free to retry;
* the process being killed between steps 1 and 2 leaves the short lease to lapse on its own,
  after which a redelivery succeeds.

What remains is a genuinely small window: if a write outlives the provisional lease (a
sub-millisecond operation against a lease measured in tens of seconds) a concurrent
redelivery could claim the key and write a second notification. That is reported rather than
hidden -- :attr:`RecordResult.confirmed` is ``False`` -- because a consumer seeing it has
found a store far slower than its configuration assumes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.domain.dedupe import DedupeKey
from app.domain.notification import Notification
from app.domain.repositories import DeduplicationStore, NotificationRepository


@dataclass(frozen=True, slots=True)
class RecordResult:
    """What happened to one attempt at recording an event's notification."""

    notification: Notification | None
    duplicate: bool
    dedupe_key: DedupeKey
    confirmed: bool = True

    @property
    def recorded(self) -> bool:
        """True when this delivery is the one that stored the notification."""
        return not self.duplicate

    def __bool__(self) -> bool:
        """Truthy when this call did the work, so ``if recorder.record(...)`` reads right."""
        return self.recorded


class NotificationRecorder:
    """Store a notification unless this event has already produced one for the user."""

    def __init__(
        self,
        repository: NotificationRepository,
        deduplication: DeduplicationStore,
    ) -> None:
        self._repository = repository
        self._deduplication = deduplication

    @property
    def repository(self) -> NotificationRepository:
        """The store this recorder writes through.

        Exposed because a consumer that has just recorded a notification usually needs to
        read it back -- to render a push payload, or to assert on the feed in the NTF-603
        test hook -- and re-resolving the store from configuration would risk pointing at a
        different backend than the one the write went to.
        """
        return self._repository

    def dedupe_key(self, notification: Notification, *, event_id: str) -> DedupeKey:
        """The key this notification would be deduplicated under.

        Exposed so a consumer can log or assert on the key without re-deriving it, which is
        the seam the NTF-603 consumer test hook needs to prove a replay was suppressed.
        """
        return DedupeKey.for_event(
            event_id,
            user_id=notification.user_id,
            notification_type=notification.type,
        )

    def _original(self, holder: str, *, user_id: uuid.UUID) -> Notification | None:
        """Resolve the notification a refused claim points at, if it is still readable.

        ``None`` is an ordinary answer here, not an error: the original may have aged out of
        the feed, or the holder may predate a change in how ids are minted. Either way the
        decision -- do not write again -- has already been made by the claim.
        """
        try:
            original_id = uuid.UUID(holder)
        except (ValueError, AttributeError, TypeError):
            return None
        return self._repository.get(original_id, user_id=user_id)

    def record(self, notification: Notification, *, event_id: str) -> RecordResult:
        """Store ``notification`` unless ``event_id`` already produced one like it."""
        key = self.dedupe_key(notification, event_id=event_id)
        holder = str(notification.id)

        claim = self._deduplication.claim(key, holder)
        if not claim.acquired:
            return RecordResult(
                notification=self._original(claim.holder, user_id=notification.user_id),
                duplicate=True,
                dedupe_key=key,
            )

        try:
            stored = self._repository.add(notification)
        except Exception:
            # Give the key back so a redelivery can retry immediately: holding a claim for
            # a notification that was never written is exactly how an outage turns into
            # silently missing notifications.
            self._deduplication.release(key, holder)
            raise

        confirmed = self._deduplication.confirm(key, holder)
        return RecordResult(
            notification=stored,
            duplicate=False,
            dedupe_key=key,
            confirmed=confirmed,
        )
