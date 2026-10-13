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

NTF-104 adds one step in front of all of this: the user's preferences decide which channels
a notification may use, and a notification left with none is not written at all. That gate
runs *before* the claim, so a suppressed notification does not burn a dedupe key that a
later replay would then be refused under.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from app.domain.dedupe import DedupeKey
from app.domain.enums import NotificationChannel
from app.domain.notification import Notification
from app.domain.preferences import NotificationPreferences
from app.domain.repositories import (
    DeduplicationStore,
    NotificationRepository,
    PreferencesRepository,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RecordResult:
    """What happened to one attempt at recording an event's notification."""

    notification: Notification | None
    duplicate: bool
    dedupe_key: DedupeKey
    confirmed: bool = True
    suppressed: bool = False
    suppressed_channels: tuple[NotificationChannel, ...] = ()

    @property
    def recorded(self) -> bool:
        """True when this delivery is the one that stored the notification."""
        return not (self.duplicate or self.suppressed)

    def __bool__(self) -> bool:
        """Truthy when this call did the work, so ``if recorder.record(...)`` reads right."""
        return self.recorded


class NotificationRecorder:
    """Store a notification unless this event has already produced one for the user."""

    def __init__(
        self,
        repository: NotificationRepository,
        deduplication: DeduplicationStore,
        preferences: PreferencesRepository | None = None,
    ) -> None:
        self._repository = repository
        self._deduplication = deduplication
        self._preferences = preferences

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

    def _preferences_for(self, user_id: uuid.UUID) -> NotificationPreferences:
        """Resolve a user's preferences, failing **open** if they cannot be read.

        The asymmetry is deliberate. Treating an unreadable preference store as "mute
        everything" would turn a Redis hiccup into a silent, service-wide notification
        outage -- the worst possible failure for a subsystem whose entire job is telling
        people things. Treating it as "no preferences set" costs a user at most one
        notification they had opted out of, which they will tell us about. One of those is
        recoverable and the other is not, so we take the recoverable one.
        """
        if self._preferences is None:
            return NotificationPreferences.defaults(user_id)
        try:
            stored = self._preferences.get(user_id)
        except Exception:
            logger.warning(
                "notification.preferences.unavailable user_id=%s -- delivering unfiltered",
                user_id,
            )
            return NotificationPreferences.defaults(user_id)
        return stored if stored is not None else NotificationPreferences.defaults(user_id)

    def record(
        self,
        notification: Notification,
        *,
        event_id: str,
        at: datetime | None = None,
    ) -> RecordResult:
        """Store ``notification`` unless the user opted out or ``event_id`` already produced one.

        ``at`` is the instant quiet hours are evaluated against; it defaults to now and exists
        so tests can place a delivery inside or outside a window without waiting for the clock.
        """
        key = self.dedupe_key(notification, event_id=event_id)

        # The preference gate runs *before* the claim on purpose. A suppressed notification
        # that burned its dedupe key would poison the event: an NTF-204 dead-letter replay,
        # issued after the user un-muted the type, would be refused as a duplicate of a
        # notification that was never written, and the user would never learn what happened.
        preferences = self._preferences_for(notification.user_id)
        permitted = preferences.permitted_channels(
            notification.type,
            notification.channels,
            at=at,
        )
        if not permitted:
            return RecordResult(
                notification=None,
                duplicate=False,
                dedupe_key=key,
                suppressed=True,
                suppressed_channels=notification.channels,
            )
        suppressed_channels = tuple(c for c in notification.channels if c not in permitted)
        notification = notification.with_channels(permitted)
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
            suppressed_channels=suppressed_channels,
        )
