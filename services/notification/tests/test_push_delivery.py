"""The send-and-record path (NTF-303).

The provider is always a fake here: what is under test is the decision around the send --
which device, how many attempts, what status is written, and what happens to a dead token --
not FCM's or APNs' HTTP behaviour (NTF-604 covers the sandboxes).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.in_memory_device_token_repository import InMemoryDeviceTokenRepository
from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.application.devices import DeviceRegistrationService
from app.application.push_delivery import MAX_VALUE_BYTES, PushDelivery
from app.domain.device_token import DeviceToken
from app.domain.enums import DeliveryStatus, DevicePlatform, NotificationChannel, NotificationType
from app.domain.notification import Notification
from app.domain.push import PushError, PushMessage
from app.domain.repositories import DeviceTokenRepository

USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ANDROID = DevicePlatform.ANDROID
IOS = DevicePlatform.IOS


class FakeGateway:
    """A provider that returns or raises whatever the test queued for it."""

    def __init__(self, platform: DevicePlatform, *outcomes: object) -> None:
        self.platform = platform
        self.outcomes = list(outcomes)
        self.sent: list[PushMessage] = []

    def send(self, message: PushMessage) -> str:
        self.sent.append(message)
        if not self.outcomes:
            return "message-id"
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return str(outcome)


def _service(
    notifications: InMemoryNotificationRepository,
    devices: DeviceRegistrationService,
    *gateways: FakeGateway,
    sleeps: list[float] | None = None,
    **kwargs: object,
) -> PushDelivery:
    return PushDelivery(
        notifications,
        devices,
        {gateway.platform: gateway for gateway in gateways},
        sleep=(sleeps if sleeps is not None else []).append,
        **kwargs,  # type: ignore[arg-type]
    )


def _store(
    notifications: InMemoryNotificationRepository,
    *,
    channels: tuple[NotificationChannel, ...] = (NotificationChannel.PUSH,),
    status: DeliveryStatus = DeliveryStatus.PENDING,
    payload: dict[str, object] | None = None,
) -> Notification:
    notification = Notification(
        user_id=USER_ID,
        type=NotificationType.ORDER_DELIVERED,
        payload=payload if payload is not None else {"orderId": "order-1"},
        channels=channels,
        status=status,
    )
    return notifications.add(notification)


def _persisted(
    notifications: InMemoryNotificationRepository, notification: Notification
) -> Notification:
    stored = notifications.get(notification.id, user_id=USER_ID)
    assert stored is not None
    return stored


@pytest.fixture
def notifications() -> InMemoryNotificationRepository:
    return InMemoryNotificationRepository()


@pytest.fixture
def devices() -> DeviceRegistrationService:
    return DeviceRegistrationService(InMemoryDeviceTokenRepository())


def _register(
    devices: DeviceRegistrationService,
    platform: DevicePlatform,
    token: str,
    *,
    minutes_ago: int = 0,
) -> DeviceToken:
    now = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return devices.register(USER_ID, platform, token, now=now)


def test_sends_to_most_recent_device_and_marks_sent(
    notifications: InMemoryNotificationRepository, devices: DeviceRegistrationService
) -> None:
    _register(devices, IOS, "ios-old", minutes_ago=5)
    _register(devices, ANDROID, "android-new")
    notification = _store(notifications)
    android = FakeGateway(ANDROID, "projects/p/messages/1")
    ios = FakeGateway(IOS, "apns-1")

    result = _service(notifications, devices, android, ios).deliver(notification)

    assert result.status is DeliveryStatus.SENT
    assert result.attempted is True
    assert result.device_id is not None
    assert result.message_id == "projects/p/messages/1"
    assert android.sent[0].token == "android-new"
    assert ios.sent == []
    assert _persisted(notifications, notification).status is DeliveryStatus.SENT


def test_records_failed_when_provider_refuses_and_does_not_retry_permanent(
    notifications: InMemoryNotificationRepository, devices: DeviceRegistrationService
) -> None:
    _register(devices, ANDROID, "android-token")
    notification = _store(notifications)
    gateway = FakeGateway(ANDROID, PushError("INVALID_ARGUMENT"))

    result = _service(notifications, devices, gateway).deliver(notification)

    assert result.status is DeliveryStatus.FAILED
    assert result.error == "INVALID_ARGUMENT"
    assert len(gateway.sent) == 1
    assert _persisted(notifications, notification).status is DeliveryStatus.FAILED


def test_retries_a_transient_failure_then_succeeds(
    notifications: InMemoryNotificationRepository, devices: DeviceRegistrationService
) -> None:
    _register(devices, ANDROID, "android-token")
    notification = _store(notifications)
    sleeps: list[float] = []
    gateway = FakeGateway(
        ANDROID,
        PushError("UNAVAILABLE", retryable=True),
        PushError("THROTTLE", retryable=True),
        "message-3",
    )

    result = _service(notifications, devices, gateway, sleeps=sleeps).deliver(notification)

    assert result.status is DeliveryStatus.SENT
    assert len(gateway.sent) == 3
    assert sleeps == [pytest.approx(0.2), pytest.approx(0.4)]


def test_exhausted_retry_budget_marks_failed(
    notifications: InMemoryNotificationRepository, devices: DeviceRegistrationService
) -> None:
    _register(devices, ANDROID, "android-token")
    notification = _store(notifications)
    sleeps: list[float] = []
    gateway = FakeGateway(
        ANDROID,
        *[PushError("SERVICE_UNAVAILABLE", retryable=True) for _ in range(3)],
    )

    result = _service(notifications, devices, gateway, sleeps=sleeps, max_attempts=3).deliver(
        notification
    )

    assert result.status is DeliveryStatus.FAILED
    assert len(gateway.sent) == 3
    assert len(sleeps) == 2
    assert _persisted(notifications, notification).status is DeliveryStatus.FAILED


def test_dead_token_is_pruned_and_never_retried(
    device_repository: DeviceTokenRepository,
) -> None:
    devices = DeviceRegistrationService(device_repository)
    _register(devices, ANDROID, "dead-token")
    notifications = InMemoryNotificationRepository()
    notification = _store(notifications)
    gateway = FakeGateway(
        ANDROID,
        PushError("UNREGISTERED", retryable=True, dead_token=True),
    )

    result = _service(notifications, devices, gateway).deliver(notification)

    assert result.status is DeliveryStatus.FAILED
    assert result.pruned is True
    assert len(gateway.sent) == 1
    assert devices.list_devices(USER_ID) == ()
    assert _persisted(notifications, notification).status is DeliveryStatus.FAILED


def test_no_device_leaves_the_notification_pending(
    notifications: InMemoryNotificationRepository, devices: DeviceRegistrationService
) -> None:
    notification = _store(notifications)
    gateway = FakeGateway(ANDROID)

    result = _service(notifications, devices, gateway).deliver(notification)

    assert result.attempted is False
    assert result.skipped == "no-reachable-device"
    assert result.status is DeliveryStatus.PENDING
    assert gateway.sent == []
    assert _persisted(notifications, notification).status is DeliveryStatus.PENDING


def test_skips_a_newer_device_on_an_unconfigured_platform(
    notifications: InMemoryNotificationRepository, devices: DeviceRegistrationService
) -> None:
    _register(devices, ANDROID, "android-reachable", minutes_ago=5)
    _register(devices, IOS, "ios-unconfigured")
    notification = _store(notifications)
    android = FakeGateway(ANDROID)

    result = _service(notifications, devices, android).deliver(notification)

    assert result.status is DeliveryStatus.SENT
    assert android.sent[0].token == "android-reachable"


def test_non_push_notification_is_skipped(
    notifications: InMemoryNotificationRepository, devices: DeviceRegistrationService
) -> None:
    _register(devices, ANDROID, "android-token")
    notification = _store(notifications, channels=(NotificationChannel.IN_APP,))
    gateway = FakeGateway(ANDROID)

    result = _service(notifications, devices, gateway).deliver(notification)

    assert result.skipped == "not-a-push-notification"
    assert gateway.sent == []


def test_terminal_notification_is_not_sent_again(
    notifications: InMemoryNotificationRepository, devices: DeviceRegistrationService
) -> None:
    _register(devices, ANDROID, "android-token")
    notification = _store(notifications, status=DeliveryStatus.SENT)
    gateway = FakeGateway(ANDROID)

    result = _service(notifications, devices, gateway).deliver(notification)

    assert result.skipped == "delivery-already-recorded"
    assert gateway.sent == []


class ExplodingRepository(InMemoryNotificationRepository):
    """A store that accepts the send's write but cannot persist the receipt."""

    def update(self, notification: Notification) -> Notification | None:
        raise RuntimeError("store unavailable")


def test_a_failed_status_write_does_not_fail_the_delivery(
    devices: DeviceRegistrationService,
) -> None:
    notifications = ExplodingRepository()
    notification = _store(notifications)
    _register(devices, ANDROID, "android-token")

    result = _service(notifications, devices, FakeGateway(ANDROID, "message-1")).deliver(
        notification
    )

    assert result.status is DeliveryStatus.SENT
    assert result.message_id == "message-1"


def test_message_payload_flattens_scalars_and_omits_unrenderable_values(
    notifications: InMemoryNotificationRepository, devices: DeviceRegistrationService
) -> None:
    _register(devices, ANDROID, "android-token")
    notification = _store(
        notifications,
        payload={
            "orderId": "order-1",
            "attempt": 2,
            "urgent": True,
            "note": None,
            "nested": {"a": 1},
            "title": "Ready",
            "body": "Your order is here",
        },
    )
    gateway = FakeGateway(ANDROID)

    _service(notifications, devices, gateway).deliver(notification)

    message = gateway.sent[0]
    assert message.title == "Ready"
    assert message.body == "Your order is here"
    assert dict(message.data) == {
        "orderId": "order-1",
        "attempt": "2",
        "urgent": "true",
        "notificationId": str(notification.id),
        "type": "order_delivered",
    }


def test_copy_falls_back_to_brand_and_type_token(
    notifications: InMemoryNotificationRepository, devices: DeviceRegistrationService
) -> None:
    _register(devices, ANDROID, "android-token")
    notification = _store(notifications)
    gateway = FakeGateway(ANDROID)

    _service(notifications, devices, gateway).deliver(notification)

    assert gateway.sent[0].title == "NutriPlan"
    assert gateway.sent[0].body == "order_delivered"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 0},
        {"backoff_seconds": -0.1},
        {"backoff_multiplier": 0.5},
    ],
)
def test_rejects_an_impossible_retry_budget(
    notifications: InMemoryNotificationRepository,
    devices: DeviceRegistrationService,
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        PushDelivery(notifications, devices, {}, **kwargs)  # type: ignore[arg-type]


def _frame_size(message: PushMessage) -> int:
    """Bytes of the provider message, token included, so the 4 KB cap is conservative."""
    return len(
        json.dumps(
            {
                "token": message.token,
                "title": message.title,
                "body": message.body,
                "data": dict(message.data),
            },
            ensure_ascii=False,
        ).encode("utf-8")
    )


class TestPayloadSize:
    """The push frame stays under the 4 KB FCM/APNs limit (NTF-304)."""

    def test_realistic_deep_link_payloads_fit(
        self, notifications: InMemoryNotificationRepository, devices: DeviceRegistrationService
    ) -> None:
        _register(devices, ANDROID, "android-token")
        order_id = str(uuid.uuid4())
        meal_id = str(uuid.uuid4())
        plan_id = str(uuid.uuid4())
        payloads = [
            {
                "orderId": order_id,
                "deepLink": f"nutriplan://order/{order_id}",
                "status": "out_for_delivery",
                "previousStatus": "preparing",
                "occurredAt": "2026-10-19T02:53:35.123456+00:00",
            },
            {
                "mealId": meal_id,
                "deepLink": f"nutriplan://meal/{meal_id}",
                "mealName": "Grilled salmon with quinoa and roasted vegetables",
                "mealType": "dinner",
                "scheduledTime": "2026-10-19T19:00:00+00:00",
                "occurredAt": "2026-10-19T02:53:35.123456+00:00",
            },
            {
                "planId": plan_id,
                "deepLink": f"nutriplan://plan/{plan_id}/renew",
                "planType": "weekly",
                "renewalDate": "2026-10-26T00:00:00+00:00",
                "occurredAt": "2026-10-19T02:53:35.123456+00:00",
            },
        ]
        gateway = FakeGateway(ANDROID)
        push = _service(notifications, devices, gateway)

        for payload in payloads:
            push.deliver(_store(notifications, payload=payload))

        assert len(gateway.sent) == len(payloads)
        assert all(_frame_size(message) <= 4096 for message in gateway.sent)

    def test_long_free_text_is_bounded_and_the_deep_link_survives(
        self, notifications: InMemoryNotificationRepository, devices: DeviceRegistrationService
    ) -> None:
        _register(devices, ANDROID, "android-token")
        notification = _store(
            notifications,
            payload={
                "mealId": "meal-1",
                "mealName": "é" * 5_000,
                "deepLink": "nutriplan://meal/meal-1",
                "title": "T" * 1_000,
                "body": "B" * 1_000,
            },
        )
        gateway = FakeGateway(ANDROID)

        _service(notifications, devices, gateway).deliver(notification)

        message = gateway.sent[0]
        data = dict(message.data)
        assert len(data["mealName"].encode("utf-8")) <= MAX_VALUE_BYTES
        assert data["mealName"].endswith("…")
        assert data["deepLink"] == "nutriplan://meal/meal-1"
        assert len(message.title.encode("utf-8")) <= MAX_VALUE_BYTES
        assert len(message.body.encode("utf-8")) <= MAX_VALUE_BYTES
        assert _frame_size(message) <= 4096
