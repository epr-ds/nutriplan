"""Translation at the provider seam (NTF-303).

The adapters raise provider-shaped errors and take provider-shaped messages. These tests pin
the one thing the wrappers own: that a provider refusal reaches the delivery service with the
retry/dead-token meaning intact, and that a :class:`PushMessage` loses nothing on the way in.
"""

from __future__ import annotations

import pytest

from app.adapters.apns_adapter import APNS_SANDBOX_URL, APNsError, APNsMessage
from app.adapters.factory import build_push_delivery, build_push_gateways
from app.adapters.fcm_adapter import FCMError, FCMMessage
from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.adapters.push_gateways import ApnsPushGateway, FcmPushGateway
from app.core.config import Settings
from app.domain.enums import DevicePlatform
from app.domain.push import PushAction, PushError, PushMessage


class FakeFcmAdapter:
    def __init__(self, *, result: str = "id", error: FCMError | None = None) -> None:
        self._result = result
        self._error = error
        self.messages: list[FCMMessage] = []

    def send(self, message: FCMMessage) -> str:
        self.messages.append(message)
        if self._error is not None:
            raise self._error
        return self._result


class FakeApnsAdapter:
    def __init__(self, *, result: str = "id", error: APNsError | None = None) -> None:
        self._result = result
        self._error = error
        self.messages: list[APNsMessage] = []

    def send(self, message: APNsMessage) -> str:
        self.messages.append(message)
        if self._error is not None:
            raise self._error
        return self._result


def _message() -> PushMessage:
    return PushMessage(
        token="token-123",
        title="Ready",
        body="Your order is here",
        data={"notificationId": "n-1", "type": "order_delivered"},
    )


def _rich_message() -> PushMessage:
    """A rich order push: image on the notification, one ``Open`` action to tap (NTF-405)."""
    return PushMessage(
        token="token-123",
        title="En camino",
        body="Tu pedido order-1 está en camino.",
        data={
            "notificationId": "n-1",
            "type": "order_in_transit",
            "deepLink": "nutriplan://order/order-1",
        },
        image_url="https://images.nutriplan.app/orders/order-1.jpg",
        actions=(PushAction(title="Open", deep_link="nutriplan://order/order-1"),),
    )


def test_fcm_gateway_forwards_the_message() -> None:
    adapter = FakeFcmAdapter(result="projects/p/messages/1")
    gateway = FcmPushGateway(adapter)  # type: ignore[arg-type]

    assert gateway.send(_message()) == "projects/p/messages/1"
    assert gateway.platform is DevicePlatform.ANDROID
    sent = adapter.messages[0]
    assert sent.token == "token-123"
    assert (sent.title, sent.body) == ("Ready", "Your order is here")
    assert sent.data == {"notificationId": "n-1", "type": "order_delivered"}
    assert sent.android is None


def test_fcm_gateway_sends_the_rich_notification_block() -> None:
    """NTF-405: image plus action becomes the FCM rich ``android`` block, not an override set."""
    adapter = FakeFcmAdapter(result="projects/p/messages/1")
    gateway = FcmPushGateway(adapter)  # type: ignore[arg-type]

    assert gateway.send(_rich_message()) == "projects/p/messages/1"
    sent = adapter.messages[0]
    assert sent.android == {
        "notification": {
            "title": "En camino",
            "body": "Tu pedido order-1 está en camino.",
            "image": "https://images.nutriplan.app/orders/order-1.jpg",
            "click_action": "nutriplan://order/order-1",
        }
    }


def test_fcm_gateway_keeps_a_plain_push_without_a_rich_block() -> None:
    """NTF-405: nothing rich to say means no ``android`` block reaches the adapter at all."""
    adapter = FakeFcmAdapter(result="projects/p/messages/1")
    gateway = FcmPushGateway(adapter)  # type: ignore[arg-type]

    gateway.send(_message())

    assert adapter.messages[0].android is None


def test_apns_gateway_merges_copy_and_data() -> None:
    adapter = FakeApnsAdapter(result="apns-1")
    gateway = ApnsPushGateway(adapter)  # type: ignore[arg-type]

    assert gateway.send(_message()) == "apns-1"
    assert gateway.platform is DevicePlatform.IOS
    sent = adapter.messages[0]
    assert sent.payload == {
        "title": "Ready",
        "body": "Your order is here",
        "notificationId": "n-1",
        "type": "order_delivered",
    }
    assert sent.image_url is None


def test_apns_gateway_passes_the_rich_image_through() -> None:
    """NTF-405: the rich image travels to the APNs client via the message, not the copy."""
    adapter = FakeApnsAdapter(result="apns-1")
    gateway = ApnsPushGateway(adapter)  # type: ignore[arg-type]

    assert gateway.send(_rich_message()) == "apns-1"
    sent = adapter.messages[0]
    assert sent.image_url == "https://images.nutriplan.app/orders/order-1.jpg"


def test_fcm_dead_token_keeps_its_meaning() -> None:
    adapter = FakeFcmAdapter(error=FCMError("UNREGISTERED", dead_token=True))
    gateway = FcmPushGateway(adapter)  # type: ignore[arg-type]

    with pytest.raises(PushError) as raised:
        gateway.send(_message())

    assert raised.value.code == "UNREGISTERED"
    assert raised.value.dead_token is True
    assert raised.value.retryable is False


def test_apns_transient_error_stays_retryable() -> None:
    adapter = FakeApnsAdapter(error=APNsError("ServiceUnavailable", retryable=True))
    gateway = ApnsPushGateway(adapter)  # type: ignore[arg-type]

    with pytest.raises(PushError) as raised:
        gateway.send(_message())

    assert raised.value.code == "ServiceUnavailable"
    assert raised.value.retryable is True
    assert raised.value.dead_token is False


def test_a_dead_token_is_never_retryable_even_when_marked_both() -> None:
    error = PushError("Unregistered", retryable=True, dead_token=True)

    assert error.dead_token is True
    assert error.retryable is False


def _configured_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "push_enabled": True,
        "fcm_project_id": "project",
        "fcm_credentials_json": '{"client_email": "svc@example.com"}',
        "apns_team_id": "team",
        "apns_key_id": "key",
        "apns_private_key": (
            "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----"
        ),
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_builds_a_gateway_only_for_each_configured_provider() -> None:
    assert build_push_gateways(Settings()) == {}

    fcm_only = build_push_gateways(_configured_settings(apns_team_id=""))
    assert set(fcm_only) == {DevicePlatform.ANDROID}

    both = build_push_gateways(_configured_settings())
    assert set(both) == {DevicePlatform.ANDROID, DevicePlatform.IOS}


def test_push_disabled_builds_no_gateway() -> None:
    assert build_push_gateways(_configured_settings(push_enabled=False)) == {}


def test_no_delivery_service_without_a_provider() -> None:
    notifications = InMemoryNotificationRepository()

    assert build_push_delivery(Settings(), notifications=notifications) is None
    assert build_push_delivery(_configured_settings(), notifications=notifications) is not None


def test_builds_an_apns_gateway_that_targets_the_sandbox_when_configured() -> None:
    """NTF-604: the delivery path sends through the provider's sandbox when it is configured.

    The adapter-level sandbox switch is pinned by the adapter tests; this pins the wiring the
    delivery service would actually use -- the gateway ``build_push_gateways`` hands to
    ``PushDelivery`` -- so a settings change cannot drift from what the tests believe to be
    true.
    """
    gateways = build_push_gateways(_configured_settings(apns_use_sandbox=True))

    assert DevicePlatform.IOS in gateways

    adapter = gateways[DevicePlatform.IOS]._adapter  # type: ignore[attr-defined]
    adapter.start()
    try:
        assert adapter._client is not None
        assert str(adapter._client.base_url).rstrip("/") == APNS_SANDBOX_URL
    finally:
        adapter.stop()
