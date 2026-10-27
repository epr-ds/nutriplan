"""NTF-707: the staging smoke journey -- synthetic order event -> push + in-app.

The staging smoke run a deploy executes is the shortest version of the product: one
synthetic commerce order event, one device, one push, and the delivery outcome has to be
visible in the event metrics by the time the run is green.

That visibility is the piece the smoke run depends on, and the runtime stack has to hand
the fan-out the event metrics it reports through. These tests pin the assembled path -- the
same one the staging deploy's smoke step drives -- so the run cannot pass with a fan-out
that never reports.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from app.adapters.fcm_adapter import FCMAdapter, FCMConfig, FCMMessage
from app.adapters.in_memory_device_token_repository import InMemoryDeviceTokenRepository
from app.application.devices import DeviceRegistrationService
from app.application.order_status_consumer import OrderStatusConsumer
from app.core.config import Settings
from app.domain.enums import DeliveryStatus, DevicePlatform, NotificationChannel, NotificationType
from app.domain.event_router import EventRouter
from app.events.consumer import DeliveredEvent
from app.events.dead_letter import InMemoryDeadLetterQueue
from app.events.dispatcher import EventDispatcher
from app.events.factory import (
    build_event_dispatcher,
    build_notification_recorder,
    build_order_progress_store,
    build_push_delivery,
)
from app.events.memory import InMemoryEventConsumer
from app.events.metrics import EventMetrics
from app.events.registry import ORDER_EVENT_VERSION, ORDER_STATUS_CHANGED, default_registry

USER = uuid.UUID("11111111-2222-3333-4444-555555555555")
ORDER_ID = "order-smoke"
EVENT_ID = "evt-smoke-order-1"
HANDLER_NAME = "app.application.order_status_consumer.OrderStatusConsumer"


class FakeFcmAdapter(FCMAdapter):
    """The provider smoke stage substitutes for FCM: accept every send, lose none."""

    def __init__(self) -> None:
        super().__init__(
            FCMConfig(
                project_id="smoke-project",
                credentials_json={"client_email": "smoke@smoke-project.iam.gserviceaccount.com"},
            )
        )
        self.sent: list[FCMMessage] = []

    def send(self, message: FCMMessage) -> str:
        self.sent.append(message)
        return "fcm-smoke-message-id"


def smoke_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Staging-shaped settings: FCM reachable, in-process state, no bus."""
    monkeypatch.setattr("app.adapters.factory.build_fcm_adapter", lambda settings: FakeFcmAdapter())
    return Settings(
        environment="staging",
        push_enabled=True,
        fcm_project_id="smoke-project",
        fcm_credentials_json=SecretStr(
            '{"client_email": "smoke@smoke-project.iam.gserviceaccount.com"}'
        ),
    )


class TestTheStagingSmokePath:
    def test_a_synthetic_order_event_pushes_and_records_the_delivery_outcome(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """NTF-707 AC: a synthetic order event reaches the device and its outcome is counted."""
        settings = smoke_settings(monkeypatch)
        device_repo = InMemoryDeviceTokenRepository()
        monkeypatch.setattr(
            "app.adapters.factory.build_device_token_repository", lambda settings: device_repo
        )
        devices = DeviceRegistrationService(device_repo)
        devices.register(USER, DevicePlatform.ANDROID, "fcm-smoke-token")

        metrics = EventMetrics()
        recorder = build_notification_recorder(settings)
        delivery = build_push_delivery(settings, notifications=recorder.repository, metrics=metrics)
        consumer = OrderStatusConsumer(
            recorder, build_order_progress_store(settings), push=delivery
        )

        event_bus = InMemoryEventConsumer()
        event_bus.ensure_group()
        dispatcher = EventDispatcher(
            event_bus,
            router=EventRouter({ORDER_STATUS_CHANGED: [HANDLER_NAME]}),
            handler_registry={HANDLER_NAME: consumer},
            registry=default_registry(),
            dead_letters=InMemoryDeadLetterQueue(),
            metrics=metrics,
        )

        event_bus.publish(
            {
                "schemaVersion": ORDER_EVENT_VERSION,
                "id": EVENT_ID,
                "type": ORDER_STATUS_CHANGED,
                "occurredAt": datetime.now(UTC).isoformat(),
                "data": {
                    "orderId": ORDER_ID,
                    "userId": str(USER),
                    "fromStatus": "confirmed",
                    "toStatus": "in_transit",
                },
            }
        )
        batch = dispatcher.poll_once(count=1, block_ms=0)

        assert batch.handled == 1

        feed = recorder.repository.list_for_user(USER)
        assert len(feed) == 1
        assert feed[0].status is DeliveryStatus.SENT
        assert set(feed[0].channels) == {NotificationChannel.IN_APP, NotificationChannel.PUSH}

        delivered = metrics.delivery_totals()[NotificationType.ORDER_IN_TRANSIT.value]
        assert delivered["delivered"] == 1
        assert delivered["failed"] == 0


class TestTheDefaultAssembledRuntimePath:
    """HRD-605: the crash-free counters have to be fed by the runtime that runs in production.

    The staging smoke wires an :class:`EventMetrics` in by hand to prove the fan-out reports.
    But the worker that a deploy actually runs assembles its dispatcher from settings alone
    (``EventWorker.from_settings``), so the assembled default path has to own those counters
    itself -- otherwise the crash-free dashboard has no delivery data to reason about.
    """

    def test_a_delivery_through_the_default_assembled_path_is_reported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = smoke_settings(monkeypatch)
        device_repo = InMemoryDeviceTokenRepository()
        monkeypatch.setattr(
            "app.adapters.factory.build_device_token_repository", lambda settings: device_repo
        )
        devices = DeviceRegistrationService(device_repo)
        devices.register(USER, DevicePlatform.ANDROID, "fcm-smoke-token")

        dispatcher = build_event_dispatcher(settings)
        batch = dispatcher.dispatch(
            DeliveredEvent(
                delivery_id=EVENT_ID,
                payload=json.dumps(
                    {
                        "schemaVersion": ORDER_EVENT_VERSION,
                        "id": EVENT_ID,
                        "type": ORDER_STATUS_CHANGED,
                        "occurredAt": datetime.now(UTC).isoformat(),
                        "data": {
                            "orderId": ORDER_ID,
                            "userId": str(USER),
                            "fromStatus": "confirmed",
                            "toStatus": "in_transit",
                        },
                    }
                ),
                attempt=1,
            )
        )

        assert batch.handled == 1
        delivered = dispatcher.metrics.delivery_totals()[NotificationType.ORDER_IN_TRANSIT.value]
        assert delivered["delivered"] == 1
        assert delivered["failed"] == 0
