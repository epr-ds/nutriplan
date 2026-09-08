"""Turn Commerce's order lifecycle events into notifications (NTF-202).

This is the first handler plugged into the NTF-201 framework, and it is where the two halves
of the service finally meet: a validated envelope goes in, and a row in somebody's feed comes
out. Everything it does sits between those two points.

The pipeline, in order
----------------------
1. **Read the status.** ``order.confirmed`` is Commerce's dedicated event for the
   ``pending -> confirmed`` move; every other transition arrives as ``order.status_changed``
   carrying ``toStatus``. Commerce emits one or the other, never both (COM-109's
   ``event_type``), so the two are handled as one path with the status resolved differently.
2. **Decide whether it is news.** ``pending`` is understood and deliberately silent. A status
   we do not recognise is not silent -- it is parked (see :mod:`app.domain.order_status`).
3. **Check the order has not already moved past it.** This is the out-of-order guard.
4. **Record**, through :class:`~app.application.notification_recorder.NotificationRecorder`,
   which applies the user's preferences (NTF-104) and the replay guard (NTF-103).
5. **Advance the mark.**

Why the guard reads before the write and the mark moves after it
----------------------------------------------------------------
The tempting shape -- advance the mark, and treat "it moved" as permission to notify -- is a
single atomic operation and it is wrong. If the recorder then fails (a Redis blip, a pod
killed mid-write), the mark has already moved past a status that was never announced. The
redelivery arrives, finds the mark ahead of it, and correctly concludes the event is stale.
The notification is lost, permanently and silently, and nothing anywhere reports it.

Reading first and advancing last inverts that. A crash between the decision and the mark
leaves the mark *behind*, so the redelivery decides to notify again -- and the dedupe store,
keyed on the producer's event id, recognises it as the same event and suppresses the second
write. The failure mode becomes "a redelivery that turns into a no-op", which is precisely
what NTF-103 was built to absorb.

The race this leaves open is two workers handling *different* statuses of one order at the
same time: both read the old mark, both notify. That is not a defect. ``preparing`` and
``in_transit`` are both real news, and the user should hear about both. What must never happen
is a *stale* status being announced, and that is prevented by the mark being monotonic -- the
store's ``advance`` is a compare-and-set, so the mark can only ever end up at the furthest
status either worker saw.

What lands in the payload
-------------------------
The feed API (NTF-105) publishes ``type`` and ``payload`` and no title or body: rendering is
the client's job, because the copy has to be localized and a server-rendered English string
would be untranslatable by the time it reached the phone. So the payload carries the *facts* a
client needs to render without a second call -- which order, what it is now, what it was --
and nothing else. Commerce's own vocabulary is preserved verbatim in ``status`` /
``previousStatus`` rather than being re-encoded into our notification types: the client already
speaks that vocabulary from the orders API, and a second dialect for the same concept would be
one more thing to keep in sync.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.application.notification_recorder import NotificationRecorder, RecordResult
from app.domain.enums import NotificationChannel, NotificationType
from app.domain.notification import Notification
from app.domain.order_status import (
    OrderStatus,
    UnknownOrderStatus,
    notification_type_for,
    progress_of,
)
from app.domain.repositories import OrderProgressStore
from app.events.envelope import EventEnvelope
from app.events.errors import MalformedEvent, UnsupportedEvent
from app.events.registry import ORDER_CONFIRMED, ORDER_STATUS_CHANGED

logger = logging.getLogger(__name__)

HANDLED_EVENT_TYPES: tuple[str, ...] = (ORDER_CONFIRMED, ORDER_STATUS_CHANGED)
"""The Commerce events this consumer subscribes to.

``order.created`` is deliberately absent. It is a valid, registered event, but an order
entering its initial state is not news to the person who just placed it -- they are looking at
the confirmation screen. NTF-201 acks an event with no handler, so leaving it out here is the
complete implementation of "we read this and chose not to act", with no code to write.
"""

DEFAULT_CHANNELS: tuple[NotificationChannel, ...] = (
    NotificationChannel.IN_APP,
    NotificationChannel.PUSH,
)
"""Order updates target both surfaces; NTF-104's preference gate narrows this per user."""


class OrderStatusConsumer:
    """Records a notification for each newsworthy, non-stale order status change."""

    def __init__(
        self,
        recorder: NotificationRecorder,
        progress: OrderProgressStore,
        *,
        channels: tuple[NotificationChannel, ...] = DEFAULT_CHANNELS,
    ) -> None:
        self._recorder = recorder
        self._progress = progress
        self._channels = channels

    # -- reading the event -------------------------------------------------------

    @staticmethod
    def _status_of(envelope: EventEnvelope) -> OrderStatus:
        """Resolve the status this event moved the order *to*.

        ``order.confirmed`` names its outcome in the event type itself, so its ``toStatus``
        is not consulted -- if the two ever disagreed, the type is the one Commerce routed on.
        """
        if envelope.type == ORDER_CONFIRMED:
            return OrderStatus.CONFIRMED
        return OrderStatus.parse(envelope.require("toStatus"))

    @staticmethod
    def _previous_status(envelope: EventEnvelope) -> str | None:
        """The status the order came from, when the producer told us.

        Optional on purpose: it is context for rendering, not a decision input, so a producer
        that omits it should not cost the user a notification.
        """
        raw = envelope.data.get("fromStatus")
        return raw if isinstance(raw, str) and raw.strip() else None

    @staticmethod
    def _user_id(envelope: EventEnvelope) -> uuid.UUID:
        """Parse the recipient, rejecting a non-uuid as permanently malformed.

        A user id we cannot parse is not a transient condition, and retrying it five times
        before parking would only delay the same conclusion.
        """
        raw = envelope.require("userId")
        try:
            return uuid.UUID(str(raw))
        except (ValueError, AttributeError, TypeError):
            raise MalformedEvent(
                f"event {envelope.event_id} ({envelope.type}) has an unusable userId {raw!r}"
            ) from None

    @staticmethod
    def _order_id(envelope: EventEnvelope) -> str:
        """The order this event is about, kept as the string Commerce sent.

        Not parsed into a ``UUID``: it is used as a store key and echoed into the payload, and
        both want the producer's own rendering. Re-formatting it here would be a second place
        that has to agree with Commerce about how an id is written down.
        """
        raw = envelope.require("orderId")
        order_id = str(raw).strip()
        if not order_id:
            raise MalformedEvent(f"event {envelope.event_id} ({envelope.type}) has a blank orderId")
        return order_id

    def _payload(
        self,
        *,
        order_id: str,
        status: OrderStatus,
        previous: str | None,
        occurred_at: datetime,
    ) -> Mapping[str, Any]:
        payload: dict[str, Any] = {
            "orderId": order_id,
            "status": status.value,
            # When the *order* moved, which is not when we recorded it -- see ``handle``.
            # A client renders "delivered at 3:04" from this, not from ``createdAt``.
            "occurredAt": occurred_at.isoformat(),
        }
        if previous is not None:
            payload["previousStatus"] = previous
        return payload

    # -- the handler -------------------------------------------------------------

    def handle(self, envelope: EventEnvelope) -> None:
        """Record the notification this event warrants, if any.

        Returning normally acks the delivery, so every "we decided not to notify" path here
        returns rather than raising -- a deliberate no-op is a successfully handled event, and
        raising would have NTF-201 retry a decision that will never come out differently.
        """
        try:
            status = self._status_of(envelope)
        except UnknownOrderStatus as exc:
            # Permanent for *this build*: parked so NTF-204 can replay it once the mapping
            # ships, rather than dropped and lost. See app.domain.order_status.
            raise UnsupportedEvent(f"event {envelope.event_id}: {exc}") from exc

        notification_type = notification_type_for(status)
        if notification_type is None:
            logger.debug(
                "notification.order.not_newsworthy event_id=%s status=%s",
                envelope.event_id,
                status.value,
            )
            return

        order_id = self._order_id(envelope)
        user_id = self._user_id(envelope)

        if not self._is_forward(order_id, status, envelope=envelope):
            return

        notification = Notification(
            user_id=user_id,
            type=notification_type,
            payload=self._payload(
                order_id=order_id,
                status=status,
                previous=self._previous_status(envelope),
                occurred_at=envelope.occurred_at,
            ),
            channels=self._channels,
            # ``created_at`` is left to default to *now*, not set to ``occurredAt``, and the
            # difference only ever matters when they diverge -- a backlog, or an NTF-204
            # replay days later. The feed is ordered by ``created_at``, so back-dating a
            # replayed notification would file it under a day the user has already scrolled
            # past and will never scroll back to: delivered, technically, and never seen. It
            # arrives at the top instead, with ``occurredAt`` in the payload so the copy can
            # still say when the order actually moved.
        )

        result = self._recorder.record(notification, event_id=envelope.event_id)
        self._log_outcome(result, envelope=envelope, order_id=order_id, status=status)

        # Only after the recorder has had its say. A mark advanced before this line would,
        # on a failed write, convince the redelivery that the event was stale. See the module
        # docstring; this ordering is the difference between a duplicate and a silent loss.
        self._progress.advance(order_id, status)

    def _is_forward(
        self,
        order_id: str,
        status: OrderStatus,
        *,
        envelope: EventEnvelope,
    ) -> bool:
        """True when ``status`` is further along than anything already announced."""
        reached = self._progress.progress_of(order_id)
        if progress_of(status) > reached:
            return True
        logger.info(
            "notification.order.stale_status event_id=%s order_id=%s status=%s already_at=%s",
            envelope.event_id,
            order_id,
            status.value,
            reached,
        )
        return False

    def _log_outcome(
        self,
        result: RecordResult,
        *,
        envelope: EventEnvelope,
        order_id: str,
        status: OrderStatus,
    ) -> None:
        if result.recorded:
            logger.info(
                "notification.order.recorded event_id=%s order_id=%s status=%s type=%s",
                envelope.event_id,
                order_id,
                status.value,
                result.dedupe_key.notification_type.value,
            )
        elif result.duplicate:
            logger.info(
                "notification.order.replayed event_id=%s order_id=%s status=%s",
                envelope.event_id,
                order_id,
                status.value,
            )
        else:
            logger.info(
                "notification.order.suppressed event_id=%s order_id=%s status=%s channels=%s",
                envelope.event_id,
                order_id,
                status.value,
                ",".join(c.value for c in result.suppressed_channels),
            )

    # -- introspection -----------------------------------------------------------

    @property
    def notification_types(self) -> tuple[NotificationType, ...]:
        """Every notification type this consumer can produce -- used by the wiring tests."""
        return tuple(
            notification_type
            for status in OrderStatus
            if (notification_type := notification_type_for(status)) is not None
        )
