"""NTF-105: the implementation conforms to ``contracts/notification.openapi.yaml``.

This is the first OpenAPI surface the notification service publishes, so the point of these
tests is to stop the two from drifting *in either direction* -- an endpoint added to the code
but not the contract is as much a defect as one documented but never built. Mobile is a
separate track working from the contract, so a silent divergence would surface as a bug in an
app that was written correctly.

The spec is located by walking up from the test file, which works in a repository checkout
(CI) but not inside the service's own test image, where only ``app/`` and ``tests/`` are
copied. So it skips locally when absent and hard-fails under CI, where it must run. Set
``NOTIFICATION_OPENAPI_SPEC`` to check it from anywhere -- e.g. against a mounted contracts
directory in a container.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.adapters import codec
from app.api.schemas import NotificationPageResponse, NotificationResponse
from app.application.feed import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.domain.enums import DeliveryStatus, NotificationChannel, NotificationType
from app.domain.notification import Notification
from app.main import app

FEED_PATH = "/notifications"
UNREAD_PATH = "/notifications/unread-count"
READ_PATH = "/notifications/{notification_id}/read"
DOCUMENTED_READ_PATH = "/notifications/{notificationId}/read"


def _schema() -> dict:
    return app.openapi()


def _aliases(model: type) -> set[str]:
    """The field names a model actually publishes on the wire."""
    return {field.alias or name for name, field in model.model_fields.items()}


# -- the implementation, on its own ----------------------------------------------------


def test_the_feed_endpoints_are_published():
    paths = _schema()["paths"]
    assert FEED_PATH in paths
    assert UNREAD_PATH in paths
    assert READ_PATH in paths


def test_the_feed_endpoints_carry_stable_operation_ids():
    """Client generators key off ``operationId``; renaming one silently renames a method in
    every generated SDK."""
    paths = _schema()["paths"]
    assert paths[FEED_PATH]["get"]["operationId"].startswith("list_notifications")
    assert paths[UNREAD_PATH]["get"]["operationId"].startswith("unread_count")
    assert paths[READ_PATH]["post"]["operationId"].startswith("mark_notification_read")


def test_list_notifications_exposes_the_expected_query_params():
    params = _schema()["paths"][FEED_PATH]["get"].get("parameters", [])
    assert {p["name"] for p in params if p["in"] == "query"} == {"unreadOnly", "page", "limit"}


def test_the_wire_shape_is_the_stored_shape_minus_the_owner():
    """NTF-102 chose a camelCase storage record specifically so a notification could reach a
    client through one mapping instead of two. This pins that promise: the published fields
    are exactly the stored ones, less ``userId`` (the caller is the owner) and plus
    ``isRead`` (stated rather than left for the client to derive). Renaming a codec key now
    fails here instead of silently changing what the API publishes."""
    sample = Notification(
        user_id=uuid.uuid4(),
        type=NotificationType.ORDER_CONFIRMED,
        created_at=datetime.now(UTC),
    )
    stored_fields = set(codec.to_record(sample))

    assert _aliases(NotificationResponse) == (stored_fields - {"userId"}) | {"isRead"}


# -- the implementation against the contract -------------------------------------------


def _locate_spec() -> Path | None:
    override = os.environ.get("NOTIFICATION_OPENAPI_SPEC")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "notification.openapi.yaml"
        if candidate.exists():
            return candidate
    return None


def _spec() -> dict:
    spec_path = _locate_spec()
    if spec_path is None:
        if os.environ.get("CI"):
            raise RuntimeError("notification.openapi.yaml not found under CI")
        pytest.skip("notification.openapi.yaml not found (local run)")

    import yaml

    return yaml.safe_load(spec_path.read_text(encoding="utf-8"))


def test_every_documented_feed_path_is_implemented():
    implemented = set(_schema()["paths"])
    documented = set(_spec()["paths"])
    # The contract documents ``{notificationId}``; FastAPI names the parameter after the
    # handler argument. Normalise the one difference rather than renaming the Python
    # argument to camelCase.
    normalised = {path.replace("{notification_id}", "{notificationId}") for path in implemented}
    assert documented <= normalised


def test_no_feed_endpoint_is_implemented_without_being_documented():
    documented = set(_spec()["paths"])
    implemented = {
        path.replace("{notification_id}", "{notificationId}")
        for path in _schema()["paths"]
        if path.startswith("/notifications")
    }
    assert implemented <= documented


def test_query_params_conform_to_the_contract():
    documented = {
        p["name"]
        for p in _spec()["paths"][FEED_PATH]["get"].get("parameters", [])
        if p["in"] == "query"
    }
    implemented = {
        p["name"]
        for p in _schema()["paths"][FEED_PATH]["get"].get("parameters", [])
        if p["in"] == "query"
    }
    assert implemented == documented


def test_the_notification_schema_conforms_to_the_contract():
    documented = set(_spec()["components"]["schemas"]["Notification"]["properties"])
    assert _aliases(NotificationResponse) == documented


def test_the_page_schema_conforms_to_the_contract():
    documented = set(_spec()["components"]["schemas"]["NotificationPage"]["properties"])
    assert _aliases(NotificationPageResponse) == documented


def test_the_documented_page_size_cap_matches_the_implementation():
    """A contract that advertised a larger cap than the service serves would send clients
    into a wall of 422s."""
    limit = next(
        p for p in _spec()["paths"][FEED_PATH]["get"]["parameters"] if p["name"] == "limit"
    )
    assert limit["schema"]["maximum"] == MAX_PAGE_SIZE
    assert limit["schema"]["default"] == DEFAULT_PAGE_SIZE


def test_the_documented_notification_types_match_the_domain():
    documented = set(_spec()["components"]["schemas"]["NotificationType"]["enum"])
    assert documented == {member.value for member in NotificationType}


def test_the_documented_delivery_statuses_match_the_domain():
    documented = set(_spec()["components"]["schemas"]["DeliveryStatus"]["enum"])
    assert documented == {member.value for member in DeliveryStatus}


def test_the_documented_channels_match_the_domain():
    documented = set(_spec()["components"]["schemas"]["NotificationChannel"]["enum"])
    assert documented == {member.value for member in NotificationChannel}
