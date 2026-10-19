"""Send a notification to every reachable device and record what each provider said (NTF-303/5).

The stored :class:`~app.domain.notification.Notification` already knows *whether* it wants a
push; this module answers the next question -- *did it get there?* -- and writes the answer
back. Three decisions shape it.

**Every reachable device, one receipt each.** A user with a phone and a tablet should be nudged
on both, so the fan-out sends to every registered device whose platform has a configured
gateway. Each device's outcome is recorded as its own
:class:`~app.domain.push_receipt.PushReceipt`, and the notification's ``status`` becomes a
*rollup*: ``SENT`` when at least one device accepted the message, ``FAILED`` when every attempt
was refused. Devices are tried most-recently-registered first -- the phone they are holding
before the tablet in a drawer -- and a device on a platform this deployment cannot reach is
skipped rather than counted as a failure. A receipt already on record for a device means a
previous run reached it, so a resumed fan-out does not send it a second nudge.

**``SENT`` means the provider accepted it.** FCM and APNs acknowledge acceptance, not
on-device display; there is no delivery receipt to wait for. So a successful send moves the
notification to ``SENT`` and leaves ``DELIVERED`` to a future client-side acknowledgement.
``FAILED`` is reserved for "we tried and gave up" -- either a permanent refusal or a retryable
one whose bounded budget ran out. A user with **no registered device** is not a failure: no
attempt was made, the notification stays ``PENDING``, and it becomes eligible again if a
device appears. Nothing in this service sweeps pending records, so that is a recorded intent
rather than a promise.

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
from app.domain.push_receipt import PushReceipt
from app.domain.repositories import NotificationRepository, PushReceiptStore

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
    """What one fan-out did, for logging, tests, and a future metrics hook (NTF-305)."""

    notification_id: uuid.UUID
    status: DeliveryStatus
    attempted: bool = False
    receipts: tuple[PushReceipt, ...] = ()
    skipped: str | None = None
    """The reason no send happened, when ``attempted`` is false."""

    @property
    def accepted(self) -> int:
        """How many devices the provider accepted the message for."""
        return sum(1 for receipt in self.receipts if receipt.accepted)

    @property
    def refused(self) -> int:
        """How many devices were refused, or had their retry budget exhausted."""
        return sum(1 for receipt in self.receipts if not receipt.accepted)


class PushDelivery:
    """Fan a recorded notification out to every reachable device, recording each receipt."""

    def __init__(
        self,
        notifications: NotificationRepository,
        devices: DeviceRegistrationService,
        gateways: Mapping[DevicePlatform, PushGateway],
        receipts: PushReceiptStore,
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
        self._receipts = receipts
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._backoff_multiplier = backoff_multiplier
        self._sleep = sleep or time.sleep

    def deliver(self, notification: Notification) -> PushDeliveryResult:
        """Fan ``notification`` out to every reachable device and persist the outcome.

        Idempotent enough to be safe on a redelivery: only a ``PENDING`` notification is
        pushed. Anything else already carries a rolled-up outcome, and re-sending would
        duplicate a nudge the user has seen (``SENT``/``DELIVERED``) or ignore the bounded
        budget that produced ``FAILED``. Within a single fan-out, a device that already has a
        receipt is skipped, so a run resumed after a partial failure does not send twice.
        """
        if not notification.targets(NotificationChannel.PUSH):
            return self._skip(notification, "not-a-push-notification")
        if notification.status is not DeliveryStatus.PENDING:
            return self._skip(notification, "delivery-already-recorded")

        devices = self._reachable_devices(notification.user_id)
        if not devices:
            return self._skip(notification, "no-reachable-device")

        attempted = False
        receipts: list[PushReceipt] = []
        for device in devices:
            existing = self._receipts.get(notification.id, device.id)
            if existing is not None:
                receipts.append(existing)
                continue
            receipts.append(self._deliver_to(notification, device))
            attempted = True

        accepted = sum(1 for receipt in receipts if receipt.accepted)
        status = DeliveryStatus.SENT if accepted else DeliveryStatus.FAILED
        self._record_status(notification, status)
        logger.info(
            "notification.push.fanout notification_id=%s devices=%d accepted=%d refused=%d",
            notification.id,
            len(receipts),
            accepted,
            len(receipts) - accepted,
        )
        return PushDeliveryResult(
            notification_id=notification.id,
            status=status,
            attempted=attempted,
            receipts=tuple(receipts),
        )

    # -- choosing destinations ---------------------------------------------------

    def _reachable_devices(self, user_id: uuid.UUID) -> list[DeviceToken]:
        """Every registered device on a platform this deployment can actually reach."""
        devices = self._devices.list_devices(user_id)
        if not devices:
            logger.info("notification.push.no_device user_id=%s", user_id)
            return []
        reachable = [device for device in devices if device.platform in self._gateways]
        if not reachable:
            logger.warning(
                "notification.push.no_gateway user_id=%s configured=%s",
                user_id,
                ",".join(platform.value for platform in self._gateways),
            )
        return reachable

    def _deliver_to(self, notification: Notification, device: DeviceToken) -> PushReceipt:
        """Send to one device and record its receipt; a refused send is not raised."""
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
            return self._record_receipt(
                PushReceipt.refused_by(
                    notification.id,
                    device.id,
                    device.platform,
                    error=exc.code,
                    pruned=pruned,
                )
            )

        logger.info(
            "notification.push.sent notification_id=%s device_id=%s platform=%s message_id=%s",
            notification.id,
            device.id,
            device.platform.value,
            message_id,
        )
        return self._record_receipt(
            PushReceipt.accepted_by(
                notification.id, device.id, device.platform, message_id=message_id
            )
        )

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

    def _record_receipt(self, receipt: PushReceipt) -> PushReceipt:
        """Persist one device's receipt, tolerating a store that cannot take it.

        The push has already happened, so a failed write is logged rather than raised: failing
        the delivery over it would report a send as broken when the send is what succeeded. The
        receipt in hand is returned either way, so the rollup still counts this device for this
        run even if the store kept nothing.
        """
        try:
            return self._receipts.record(receipt)
        except Exception:
            logger.warning(
                "notification.push.receipt_write_failed notification_id=%s device_id=%s",
                receipt.notification_id,
                receipt.device_id,
                exc_info=True,
            )
            return receipt

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
