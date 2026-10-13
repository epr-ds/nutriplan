"""NTF-104: the preferences endpoints conform to ``contracts/notification.openapi.yaml``.

Same two-way gate as ``test_feed_contract.py`` -- and in fact that module's path tests already
cover the new route in both directions, since they compare whole path sets. What is added here
is the *shape*: the four schemas, the enum parity, and the handful of details that are easy to
get subtly wrong and impossible to notice from either side alone.

Three of those are worth naming.

``pattern`` rather than ``format: time``: OpenAPI's ``time`` is RFC 3339 ``full-time``, which
*requires* an offset. An offset is exactly what a quiet-hours boundary must not carry, so a
generated client that trusted ``format: time`` would send ``22:00:00-06:00`` and get a 422.

``types`` in ``required``: omitting a row resets it, so a client that forgot the field would
otherwise be silently switching every notification back on.

The documented ``timeZone`` default: a client that omits the field gets the service's default,
and a contract advertising a different one would put the user's quiet hours in the wrong part
of the day -- the sort of bug that looks like a timezone rounding error and is not one.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.api.schemas import (
    _TIME_PATTERN,
    NotificationPreferencesResponse,
    QuietHoursSchema,
    TypePreferenceSchema,
    UpdateNotificationPreferencesRequest,
)
from app.domain.enums import NotificationType
from app.domain.quiet_hours import DEFAULT_TIME_ZONE
from app.main import app

PATH = "/notifications/preferences"


def _schema() -> dict:
    return app.openapi()


def _aliases(model: type) -> set[str]:
    return {field.alias or name for name, field in model.model_fields.items()}


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


def _schemas() -> dict:
    return _spec()["components"]["schemas"]


# -- the implementation, on its own ----------------------------------------------------


def test_both_preference_operations_are_published():
    published = _schema()["paths"]
    assert PATH in published
    assert {"get", "put"} <= set(published[PATH])


def test_the_preference_operations_carry_stable_operation_ids():
    """Client generators key off ``operationId``; renaming one renames a method in every SDK."""
    published = _schema()["paths"][PATH]
    assert published["get"]["operationId"].startswith("get_preferences")
    assert published["put"]["operationId"].startswith("replace_preferences")


def test_the_preference_operations_take_no_parameters():
    """The subject comes from the token. A ``userId`` parameter here would be the whole bug."""
    published = _schema()["paths"][PATH]
    assert published["get"].get("parameters", []) == []
    assert published["put"].get("parameters", []) == []


# -- the implementation against the contract -------------------------------------------


def test_both_operations_are_documented():
    documented = _spec()["paths"]
    assert PATH in documented
    assert {"get", "put"} <= set(documented[PATH])


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("QuietHours", QuietHoursSchema),
        ("TypePreference", TypePreferenceSchema),
        ("NotificationPreferences", NotificationPreferencesResponse),
        ("UpdateNotificationPreferencesRequest", UpdateNotificationPreferencesRequest),
    ],
)
def test_the_documented_schema_matches_the_model(name, model):
    assert _aliases(model) == set(_schemas()[name]["properties"])


def test_the_documented_type_enum_matches_the_domain():
    """``TypePreference.type`` refs the shared ``NotificationType``, which the feed contract
    already pins to the domain -- so a new member cannot reach the settings screen undeclared."""
    assert _schemas()["TypePreference"]["properties"]["type"] == {
        "$ref": "#/components/schemas/NotificationType"
    }
    assert set(_schemas()["NotificationType"]["enum"]) == {m.value for m in NotificationType}


def test_types_is_required_on_a_replacement():
    """A defaulted ``types`` would turn a forgotten field into "switch everything back on"."""
    assert "types" in _schemas()["UpdateNotificationPreferencesRequest"]["required"]


def test_quiet_hours_boundaries_are_documented_as_a_pattern_not_a_time_format():
    for field in ("start", "end"):
        documented = _schemas()["QuietHours"]["properties"][field]
        assert documented["pattern"] == _TIME_PATTERN
        assert "format" not in documented


def test_both_boundaries_are_required_on_a_window():
    """A window with one end is not a window; the domain would have to invent the other."""
    assert set(_schemas()["QuietHours"]["required"]) == {"start", "end"}


def test_the_documented_time_zone_default_is_the_one_the_service_applies():
    """A client that omits ``timeZone`` gets the service's default. Advertising a different
    one would put the user's quiet hours in the wrong part of the day."""
    assert _schemas()["QuietHours"]["properties"]["timeZone"]["default"] == DEFAULT_TIME_ZONE


def test_quiet_hours_is_documented_as_nullable_on_both_sides():
    """``null`` is how a window is cleared *and* how "none set" is reported."""
    for name in ("NotificationPreferences", "UpdateNotificationPreferencesRequest"):
        assert _schemas()[name]["properties"]["quietHours"]["nullable"] is True


def test_a_renamed_contract_field_fails_the_gate(tmp_path, monkeypatch):
    """The gate is only worth having if it can fail. Drift a field in a copy of the spec and
    watch the schema comparison catch it."""
    spec_path = _locate_spec()
    if spec_path is None:
        pytest.skip("notification.openapi.yaml not found (local run)")

    mutated = spec_path.read_text(encoding="utf-8").replace("        quietHours:", "        night:")
    target = tmp_path / "notification.openapi.yaml"
    target.write_text(mutated, encoding="utf-8")
    monkeypatch.setenv("NOTIFICATION_OPENAPI_SPEC", str(target))

    with pytest.raises(AssertionError):
        test_the_documented_schema_matches_the_model(
            "NotificationPreferences", NotificationPreferencesResponse
        )
