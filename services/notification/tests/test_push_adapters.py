"""The synchronous provider clients, exercised without a provider.

These are the NTF-301 adapters after NTF-303 made them synchronous and taught their error
classification the difference between "try again" and "this address is dead". The HTTP
transport is faked, so the assertions are about the request we build and the error we raise,
not about FCM or APNs (NTF-604 covers the sandboxes).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable

import httpx
import pytest

from app.adapters.apns_adapter import (
    APNS_SANDBOX_URL,
    APNsAdapter,
    APNsConfig,
    APNsError,
    APNsMessage,
)
from app.adapters.fcm_adapter import FCMAdapter, FCMConfig, FCMError, FCMMessage

Handler = Callable[[httpx.Request], httpx.Response]


def _fcm(handler: Handler) -> FCMAdapter:
    adapter = FCMAdapter(
        FCMConfig(project_id="project", credentials_json={"client_email": "svc@example.com"})
    )
    adapter._client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter._access_token = "access-token"
    adapter._token_expiry = time.time() + 3600
    return adapter


def _apns(handler: Handler, *, use_sandbox: bool = False) -> APNsAdapter:
    adapter = APNsAdapter(
        APNsConfig(
            key_id="key-id",
            team_id="team-id",
            auth_key=b"pem",
            bundle_id="mx.nutriplan.app",
            use_sandbox=use_sandbox,
        )
    )
    base_url = APNS_SANDBOX_URL if use_sandbox else "https://api.push.apple.com"
    adapter._client = httpx.Client(base_url=base_url, transport=httpx.MockTransport(handler))
    adapter._access_token = "provider-token"
    adapter._token_expiry = time.time() + 3600
    return adapter


def _message() -> FCMMessage:
    return FCMMessage(
        token="device-token",
        title="Ready",
        body="Your order is here",
        data={"notificationId": "n-1"},
    )


def test_fcm_sends_the_expected_body_and_returns_the_message_name() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"name": "projects/project/messages/1"})

    adapter = _fcm(handler)
    try:
        assert adapter.send(_message()) == "projects/project/messages/1"
    finally:
        adapter.stop()

    request = seen[0]
    assert str(request.url) == "https://fcm.googleapis.com/v1/projects/project/messages:send"
    assert request.headers["authorization"] == "Bearer access-token"
    body = json.loads(request.content)
    assert body["message"]["token"] == "device-token"
    assert body["message"]["notification"] == {
        "title": "Ready",
        "body": "Your order is here",
    }
    assert body["message"]["data"] == {"notificationId": "n-1"}
    assert body["message"].get("android") is None


def test_fcm_sends_the_rich_notification_block() -> None:
    """NTF-405: an image and a click action travel to FCM as the rich ``android`` block."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"name": "projects/project/messages/1"})

    adapter = _fcm(handler)
    try:
        assert (
            adapter.send(
                FCMMessage(
                    token="device-token",
                    title="En camino",
                    body="Tu pedido order-1 está en camino.",
                    data={"notificationId": "n-1", "deepLink": "nutriplan://order/order-1"},
                    android={
                        "notification": {
                            "title": "En camino",
                            "body": "Tu pedido order-1 está en camino.",
                            "image": "https://images.nutriplan.app/orders/order-1.jpg",
                            "click_action": "nutriplan://order/order-1",
                        }
                    },
                )
            )
            == "projects/project/messages/1"
        )
    finally:
        adapter.stop()

    body = json.loads(seen[0].content)
    assert body["message"]["android"] == {
        "notification": {
            "title": "En camino",
            "body": "Tu pedido order-1 está en camino.",
            "image": "https://images.nutriplan.app/orders/order-1.jpg",
            "click_action": "nutriplan://order/order-1",
        }
    }


def test_fcm_unregistered_is_a_dead_token() -> None:
    adapter = _fcm(lambda _: httpx.Response(404, json={"error": {"status": "UNREGISTERED"}}))
    try:
        with pytest.raises(FCMError) as raised:
            adapter.send(_message())
    finally:
        adapter.stop()

    assert raised.value.code == "UNREGISTERED"
    assert raised.value.dead_token is True
    assert raised.value.retryable is False


def test_fcm_transient_status_is_retryable() -> None:
    adapter = _fcm(lambda _: httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}}))
    try:
        with pytest.raises(FCMError) as raised:
            adapter.send(_message())
    finally:
        adapter.stop()

    assert raised.value.retryable is True
    assert raised.value.dead_token is False


def test_fcm_non_json_error_body_is_retryable() -> None:
    adapter = _fcm(lambda _: httpx.Response(502, text="<html>bad gateway</html>"))
    try:
        with pytest.raises(FCMError) as raised:
            adapter.send(_message())
    finally:
        adapter.stop()

    assert raised.value.code == "UNKNOWN"
    assert raised.value.retryable is True


def _apns_message() -> APNsMessage:
    return APNsMessage(
        token="device-token",
        payload={"title": "Ready", "body": "Your order is here", "id": "notification-1"},
        badge=4,
    )


def test_apns_sends_the_alert_and_custom_keys() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"apns-id": "apns-1"})

    adapter = _apns(handler)
    try:
        assert adapter.send(_apns_message()) == "apns-1"
    finally:
        adapter.stop()

    request = seen[0]
    assert str(request.url) == "https://api.push.apple.com/3/device-token"
    assert request.headers["apns-topic"] == "mx.nutriplan.app"
    assert request.headers["apns-id"] == "notification-1"
    body = json.loads(request.content)
    assert body["aps"]["alert"] == {"title": "Ready", "body": "Your order is here"}
    assert body["aps"]["badge"] == 4
    assert body["id"] == "notification-1"
    assert "mutable-content" not in body["aps"]
    assert "attachment" not in body["aps"]


def test_apns_sends_the_rich_notification_with_image() -> None:
    """NTF-405: a rich push makes the APNs copy mutable and attaches the image."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"apns-id": "apns-1"})

    adapter = _apns(handler)
    try:
        assert (
            adapter.send(
                APNsMessage(
                    token="device-token",
                    payload={
                        "title": "En camino",
                        "body": "Tu pedido order-1 está en camino.",
                        "id": "notification-1",
                        "deepLink": "nutriplan://order/order-1",
                    },
                    badge=1,
                    image_url="https://images.nutriplan.app/orders/order-1.jpg",
                )
            )
            == "apns-1"
        )
    finally:
        adapter.stop()

    body = json.loads(seen[0].content)
    assert body["aps"]["alert"] == {
        "title": "En camino",
        "body": "Tu pedido order-1 está en camino.",
    }
    assert body["aps"]["badge"] == 1
    assert body["aps"]["mutable-content"] == 1
    assert body["aps"]["attachment"] == {"url": "https://images.nutriplan.app/orders/order-1.jpg"}
    assert body["aps"].get("sound", "default") == "default"


def test_apns_unregistered_is_a_dead_token() -> None:
    adapter = _apns(lambda _: httpx.Response(410, json={"reason": "Unregistered"}))
    try:
        with pytest.raises(APNsError) as raised:
            adapter.send(_apns_message())
    finally:
        adapter.stop()

    assert raised.value.dead_token is True
    assert raised.value.retryable is False


def test_apns_expired_provider_token_is_retryable_and_dropped() -> None:
    adapter = _apns(lambda _: httpx.Response(403, json={"reason": "ExpiredProviderToken"}))
    try:
        with pytest.raises(APNsError) as raised:
            adapter.send(_apns_message())
    finally:
        adapter.stop()

    assert raised.value.retryable is True
    assert adapter._access_token is None


def test_apns_sandbox_switches_the_endpoint() -> None:
    adapter = APNsAdapter(
        APNsConfig(
            key_id="key-id",
            team_id="team-id",
            auth_key=b"pem",
            bundle_id="mx.nutriplan.app",
            use_sandbox=True,
        )
    )
    adapter.start()
    try:
        assert adapter._client is not None
        assert str(adapter._client.base_url).rstrip("/") == APNS_SANDBOX_URL
    finally:
        adapter.stop()
