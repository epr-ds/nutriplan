"""Send one notification to one device and record what the provider said (NTF-303).

The stored :class:`~app.domain.notification.Notification` already knows *whether* it wants a
push; this module answers the next question -- *did it get there?* -- and writes the answer
back onto the record. Three decisions shape it.

**One device, not every device.** NTF-305 owns multi-device fan-out and per-device receipts;
this slice deliberately picks one reachable destination so that the notification's single
``status`` has one unambiguous meaning. The chosen device is the most recently registered one
whose platform has a configured gateway, which is both the best single guess at "the phone
they are holding" and a graceful degradation when only one provider is configured. Selecting
by recency alone would fail a user whose newest device is on the platform this deployment
cannot reach while an older, reachable device sits right behind it.

**``SENT`` means the provider accepted it.** FCM and APNs acknowledge acceptance, not
on-device display; there is no delivery receipt to wait for. So a successful send moves the
notification to ``SENT`` and leaves ``DELIVERED`` to a future client-side acknowledgement.
``FAILED`` is reserved for "we tried and gave up" -- either a permanent refusal or a retryable
one whose bounded budget ran out. A user with **no registered device** is not a failure: no
attempt was made, the notification stays ``PENDING``, and it becomes eligible again if a
device appears. Nothing in this service currently sweeps pending records, so that is a
recorded intent rather than a promise; NTF-305 is where re-attempting belongs.

**A provider refusal stays out of the event ack.** A send failure is recorded as status,
never raised: the event *was* handled, and re-raising would park it on the dead-letter queue
for a condition a replay cannot fix (the notification is deduplicated, so a retry would not
send again). The bounded retry loop is therefore in-process, with short backoff, and the
caller gets a result either way.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from app.application.devices import DeviceRegistrationService
from app.domain.device_token import DeviceToken
from app.domain.enums import DeliveryStatus, DevicePlatform, NotificationChannel
from app.domain.notification import Notification
from app.domain.push import PushError, PushGateway, PushMessage
from app.domain.repositories import NotificationRepository

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "NutriPlan"
"""Brand name, so it is not a translation. NTF-401 replaces the body with localized copy."""

MAX_VALUE_BYTES = 256
"""FCM and APNs cap a whole message at 4 KB (NTF-304).

Push data is a routing hint -- the deep link, the entity id, the type -- and the app fetches
the screen's content by id, so a long free-text field (a meal name) is shortened here rather
than allowed to push the frame over the provider's limit. The stored notification keeps the
full value for the in-app feed. The limit is per *encoded* value and generous next to every
field the producers actually send, so truncation only ever affects pathological input.
"""


def _truncate(value: str) -> str:
    """Shorten one value to ``MAX_VALUE_BYTES`` of UTF-8 without splitting a character."""
    encoded = value.encode("utf-8")
    if len(encoded) <= MAX_VALUE_BYTES:
        return value
    suffix = "…".encode()
    return encoded[: MAX_VALUE_BYTES - len(suffix)].decode("utf-8", "ignore") + "…"


@dataclass(frozen=True, slots=True)
class PushDeliveryResult:
    """What one delivery attempt did, for logging, tests, and a future metrics hook."""

    notification_id: uuid.UUID
    status: DeliveryStatus
    attempted: bool = False
    device_id: uuid.UUID | None = None
    message_id: str | None = None
    error: str | None = None
    pruned: bool = False
    skipped: str | None = None
    """The reason no send happened, when ``attempted`` is false."""


class PushDelivery:
    """Deliver a recorded notification through its device's provider and record the receipt."""

    def __init__(
        self,
        notifications: NotificationRepository,
        devices: DeviceRegistrationService,
        gateways: Mapping[DevicePlatform, PushGateway],
        *,
        max_attempts: int = 3,
        backoff_seconds: float = 0.2,
        backoff_multiplier: float = 2.0,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds must not be negative")
        if backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be at least 1")
        self._notifications = notifications
        self._devices = devices
        self._gateways = {
            DevicePlatform(platform): gateway for platform, gateway in gateways.items()
        }
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._backoff_multiplier = backoff_multiplier
        self._sleep = sleep or time.sleep

    def deliver(self, notification: Notification) -> PushDeliveryResult:
        """Send ``notification`` to one reachable device and persist the outcome.

        Idempotent enough to be safe on a redelivery: only a ``PENDING`` notification is
        pushed. Anything else already carries an outcome, and re-sending would either duplicate
        a nudge the user has seen (``SENT``/``DELIVERED``) or ignore the bounded budget that
        produced ``FAILED``. A separate re-attempt policy belongs to NTF-305, not here.
        """
        if not notification.targets(NotificationChannel.PUSH):
            return self._skip(notification, "not-a-push-notification")
        if notification.status is not DeliveryStatus.PENDING:
            return self._skip(notification, "delivery-already-recorded")

        device = self._choose_device(notification.user_id)
        if device is None:
            return self._skip(notification, "no-reachable-device")

        gateway = self._gateways[device.platform]
        message = self._build_message(notification, device.token)
        try:
            message_id = self._send(gateway, message)
        except PushError as exc:
            pruned = self._prune_if_dead(device, exc)
            logger.warning(
                "notification.push.failed notification_id=%s device_id=%s platform=%s "
                "code=%s retryable=%s dead_token=%s pruned=%s",
                notification.id,
                device.id,
                device.platform.value,
                exc.code,
                exc.retryable,
                exc.dead_token,
                pruned,
            )
            self._record_status(notification, DeliveryStatus.FAILED)
            return PushDeliveryResult(
                notification_id=notification.id,
                status=DeliveryStatus.FAILED,
                attempted=True,
                device_id=device.id,
                error=exc.code,
                pruned=pruned,
            )

        logger.info(
            "notification.push.sent notification_id=%s device_id=%s platform=%s message_id=%s",
            notification.id,
            device.id,
            device.platform.value,
            message_id,
        )
        self._record_status(notification, DeliveryStatus.SENT)
        return PushDeliveryResult(
            notification_id=notification.id,
            status=DeliveryStatus.SENT,
            attempted=True,
            device_id=device.id,
            message_id=message_id,
        )

    # -- choosing a destination --------------------------------------------------

    def _choose_device(self, user_id: uuid.UUID) -> DeviceToken | None:
        """The most recent device on a platform this deployment can actually reach."""
        devices = self._devices.list_devices(user_id)
        if not devices:
            logger.info("notification.push.no_device user_id=%s", user_id)
            return None
        for device in devices:
            if device.platform in self._gateways:
                return device
        logger.warning(
            "notification.push.no_gateway user_id=%s configured=%s",
            user_id,
            ",".join(platform.value for platform in self._gateways),
        )
        return None

    # -- the send, with bounded retries -----------------------------------------

    def _send(self, gateway: PushGateway, message: PushMessage) -> str:
        """Call ``gateway`` up to ``max_attempts`` times, sleeping between retryable failures."""
        attempt = 0
        while True:
            attempt += 1
            try:
                return gateway.send(message)
            except PushError as exc:
                if exc.dead_token or not exc.retryable or attempt >= self._max_attempts:
                    raise
                delay = self._backoff_seconds * (self._backoff_multiplier ** (attempt - 1))
                logger.info(
                    "notification.push.retry token=%s attempt=%d delay_seconds=%.3f code=%s",
                    message.token[-8:],
                    attempt,
                    delay,
                    exc.code,
                )
                self._sleep(delay)

    # -- receipts ----------------------------------------------------------------

    def _record_status(self, notification: Notification, status: DeliveryStatus) -> None:
        """Persist ``status``, tolerating a store that cannot take it.

        The push has already happened by the time this runs, so a failed write must not turn
        into an exception the consumer reports as an unhandled event: a replay would not send
        again (the notification is deduplicated) and would fail the same way. The warning is
        the signal; the record stays ``PENDING`` and is visibly wrong rather than silently
        worse.
        """
        updated = notification.with_status(status)
        if updated is notification:
            return
        try:
            stored = self._notifications.update(updated)
        except Exception:
            logger.warning(
                "notification.push.status_write_failed notification_id=%s status=%s",
                notification.id,
                status.value,
                exc_info=True,
            )
            return
        if stored is None:
            logger.info(
                "notification.push.status_dropped notification_id=%s status=%s reason=expired",
                notification.id,
                status.value,
            )

    def _prune_if_dead(self, device: DeviceToken, exc: PushError) -> bool:
        """Forget a token the provider says will never work again.

        A store failure here is logged rather than raised: the dead token is a clean-up, and
        failing the delivery over it would report a send as broken when the send is what
        told us the address was bad.
        """
        if not exc.dead_token:
            return False
        try:
            return self._devices.prune(device.platform, device.token)
        except Exception:
            logger.warning(
                "notification.push.prune_failed device_id=%s platform=%s",
                device.id,
                device.platform.value,
                exc_info=True,
            )
            return False

    # -- rendering ---------------------------------------------------------------

    def _build_message(self, notification: Notification, token: str) -> PushMessage:
        """Render the provider-neutral message from the stored notification.

        Title and body come from the payload when a producer supplied them. Otherwise they
        fall back to the brand and the *type token* -- deliberately not an English sentence,
        because NTF-401 owns localized copy and a hard-coded one here would quietly become a
        second, untranslated catalogue. Scalars from the payload are flattened into ``data``
        so the client can deep-link without the service inventing a schema (NTF-304).
        """
        payload = notification.payload
        return PushMessage(
            token=token,
            title=_truncate(str(payload.get("title") or DEFAULT_TITLE)),
            body=_truncate(str(payload.get("body") or notification.type.value)),
            data=self._data(notification),
        )

    @staticmethod
    def _data(notification: Notification) -> dict[str, str]:
        """FCM and APNs both require string data values; flatten the JSON-native scalars."""
        data: dict[str, str] = {}
        for key, value in notification.payload.items():
            if key in {"title", "body"} or value is None:
                continue
            if isinstance(value, bool):
                data[key] = "true" if value else "false"
            elif isinstance(value, (str, int, float)):
                data[key] = _truncate(str(value))
        # Written last so a producer cannot shadow the fields the client relies on.
        data["notificationId"] = str(notification.id)
        data["type"] = notification.type.value
        return data

    @staticmethod
    def _skip(notification: Notification, reason: str) -> PushDeliveryResult:
        return PushDeliveryResult(
            notification_id=notification.id,
            status=notification.status,
            skipped=reason,
        )
