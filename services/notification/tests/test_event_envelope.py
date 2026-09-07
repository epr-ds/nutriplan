"""Parsing a raw stream payload into a validated envelope (NTF-201).

The boundary these tests guard is the only place this service trusts bytes off the bus, so
they are written from the outside in: what commerce actually publishes must parse, and
everything else must fail in a way the dispatcher can act on.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.events.envelope import EventEnvelope, parse_envelope
from app.events.errors import MalformedEvent

# --------------------------------------------------------------------------------------
# The literal shape ``services/commerce/app/events/envelope.py::to_envelope`` produces.
#
# Captured rather than imported: the two services are separate deployables with separate
# test containers, so notification cannot import commerce's code. That makes this constant a
# hand-maintained copy of a cross-service contract, which is worth stating plainly -- if
# commerce changes its envelope without changing this, the drift shows up as a production
# incident rather than a red test. ``tests/test_event_registry.py`` narrows the gap by
# pinning the field names the registry requires against the same source.
# --------------------------------------------------------------------------------------
COMMERCE_ORDER_CONFIRMED = {
    "schemaVersion": 1,
    "id": "6f1e3a5c-2b90-4f4e-9a1a-0d2c4b8e7f31",
    "type": "order.confirmed",
    "occurredAt": "2026-07-12T21:00:00+00:00",
    "data": {
        "orderId": "0f7d9a1e-4c33-4a5b-8e21-1b6f0c2d3e45",
        "userId": "b3a1c9d7-5e42-4f18-9c60-7a8b2d4e6f09",
        "fromStatus": "pending",
        "toStatus": "confirmed",
    },
}


def envelope(**overrides: object) -> dict[str, object]:
    """A valid envelope with ``overrides`` applied, for the failure cases."""
    return {**COMMERCE_ORDER_CONFIRMED, **overrides}


class TestParsingWhatCommercePublishes:
    def test_the_published_json_round_trips_into_a_typed_envelope(self) -> None:
        parsed = parse_envelope(json.dumps(COMMERCE_ORDER_CONFIRMED))

        assert parsed == EventEnvelope(
            schema_version=1,
            event_id="6f1e3a5c-2b90-4f4e-9a1a-0d2c4b8e7f31",
            type="order.confirmed",
            occurred_at=datetime(2026, 7, 12, 21, 0, tzinfo=UTC),
            data=COMMERCE_ORDER_CONFIRMED["data"],  # type: ignore[arg-type]
        )

    def test_an_already_decoded_mapping_parses_the_same_way(self) -> None:
        """The in-process adapter and most tests hand over a dict, not JSON text."""
        assert parse_envelope(COMMERCE_ORDER_CONFIRMED) == parse_envelope(
            json.dumps(COMMERCE_ORDER_CONFIRMED)
        )

    def test_bytes_parse_too(self) -> None:
        """A client without ``decode_responses`` hands over bytes; that is not a defect."""
        raw = json.dumps(COMMERCE_ORDER_CONFIRMED).encode("utf-8")

        assert parse_envelope(raw).type == "order.confirmed"

    def test_the_envelope_is_immutable(self) -> None:
        """A handler must not be able to edit an event on its way to the next one."""
        parsed = parse_envelope(COMMERCE_ORDER_CONFIRMED)

        with pytest.raises(AttributeError):
            parsed.type = "order.cancelled"  # type: ignore[misc]


class TestForwardCompatibility:
    def test_an_unknown_top_level_key_is_ignored(self) -> None:
        """Commerce adding an envelope field must not take this consumer down."""
        parsed = parse_envelope(envelope(traceId="abc-123", region="mx-central"))

        assert parsed.type == "order.confirmed"

    def test_an_unknown_data_key_is_kept_but_not_required(self) -> None:
        """Additive payload change is the common case; it has to be a non-event."""
        payload = envelope(data={**COMMERCE_ORDER_CONFIRMED["data"], "channel": "web"})  # type: ignore[dict-item]

        parsed = parse_envelope(payload)

        assert parsed.data["channel"] == "web"
        assert parsed.data["orderId"] == COMMERCE_ORDER_CONFIRMED["data"]["orderId"]  # type: ignore[index]

    def test_a_missing_data_object_becomes_empty_rather_than_an_error(self) -> None:
        """So the registry reports *which* fields are missing, which is more actionable."""
        payload = {k: v for k, v in COMMERCE_ORDER_CONFIRMED.items() if k != "data"}

        assert parse_envelope(payload).data == {}

    def test_the_parsed_data_is_a_copy(self) -> None:
        """Two handlers see the same event; one must not be able to edit the other's copy."""
        source = dict(COMMERCE_ORDER_CONFIRMED)
        source["data"] = dict(source["data"])  # type: ignore[arg-type]

        parsed = parse_envelope(source)
        source["data"]["orderId"] = "mutated"  # type: ignore[index]

        assert parsed.data["orderId"] != "mutated"


class TestRejectingWhatCannotBeRead:
    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            pytest.param("not json at all", "not valid JSON", id="not-json"),
            pytest.param("[1, 2, 3]", "expected an object", id="json-array"),
            pytest.param('"a string"', "expected an object", id="json-string"),
            pytest.param("null", "expected an object", id="json-null"),
        ],
    )
    def test_a_payload_that_is_not_a_json_object_is_malformed(
        self, payload: str, expected: str
    ) -> None:
        with pytest.raises(MalformedEvent, match=expected):
            parse_envelope(payload)

    @pytest.mark.parametrize("field", ["schemaVersion", "id", "type", "occurredAt"])
    def test_every_required_envelope_field_is_required(self, field: str) -> None:
        payload = {k: v for k, v in COMMERCE_ORDER_CONFIRMED.items() if k != field}

        with pytest.raises(MalformedEvent, match=field):
            parse_envelope(payload)

    def test_all_missing_fields_are_reported_at_once(self) -> None:
        """One round trip through the log should be enough to fix a broken producer."""
        with pytest.raises(MalformedEvent) as exc:
            parse_envelope({"schemaVersion": 1})

        message = str(exc.value)
        assert "id" in message and "type" in message and "occurredAt" in message

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            pytest.param("1", "must be an integer", id="string"),
            pytest.param(1.0, "must be an integer", id="float"),
            pytest.param(None, "must be an integer", id="null"),
            pytest.param(0, "must be positive", id="zero"),
            pytest.param(-1, "must be positive", id="negative"),
        ],
    )
    def test_the_schema_version_must_be_a_positive_integer(
        self, value: object, expected: str
    ) -> None:
        with pytest.raises(MalformedEvent, match=expected):
            parse_envelope(envelope(schemaVersion=value))

    def test_a_boolean_schema_version_is_not_read_as_version_one(self) -> None:
        """``isinstance(True, int)`` is true in Python, so this needs its own guard."""
        with pytest.raises(MalformedEvent, match="must be an integer"):
            parse_envelope(envelope(schemaVersion=True))

    @pytest.mark.parametrize("field", ["id", "type"])
    @pytest.mark.parametrize(
        "value", ["", "   ", pytest.param(42, id="int"), pytest.param(None, id="null")]
    )
    def test_identifiers_must_be_non_blank_strings(self, field: str, value: object) -> None:
        with pytest.raises(MalformedEvent, match=field):
            parse_envelope(envelope(**{field: value}))

    def test_identifiers_are_stripped(self) -> None:
        """Whitespace around an id would otherwise change the NTF-103 dedupe digest."""
        parsed = parse_envelope(envelope(id="  evt-1  ", type=" order.confirmed "))

        assert parsed.event_id == "evt-1"
        assert parsed.type == "order.confirmed"

    def test_data_must_be_an_object_when_present(self) -> None:
        with pytest.raises(MalformedEvent, match="data must be an object"):
            parse_envelope(envelope(data=["orderId", "userId"]))


class TestTheTimestampMustCarryAnOffset:
    def test_an_unparseable_timestamp_is_malformed(self) -> None:
        with pytest.raises(MalformedEvent, match="not an ISO-8601 timestamp"):
            parse_envelope(envelope(occurredAt="last Tuesday"))

    def test_a_naive_timestamp_is_rejected_rather_than_assumed_utc(self) -> None:
        """Quiet hours (NTF-104) makes an hour of drift a push at 3am, not a rounding error."""
        with pytest.raises(MalformedEvent, match="must carry a UTC offset"):
            parse_envelope(envelope(occurredAt="2026-07-12T21:00:00"))

    def test_a_non_utc_offset_is_preserved_as_the_same_instant(self) -> None:
        """Commerce may run anywhere; what matters is the instant, not the spelling."""
        parsed = parse_envelope(envelope(occurredAt="2026-07-12T15:00:00-06:00"))

        assert parsed.occurred_at == datetime(2026, 7, 12, 21, 0, tzinfo=UTC)
        assert parsed.occurred_at.utcoffset() == timedelta(hours=-6)

    def test_a_z_suffix_parses(self) -> None:
        """Python 3.11+ accepts ``Z``; asserted so a runtime downgrade cannot go unnoticed."""
        assert parse_envelope(envelope(occurredAt="2026-07-12T21:00:00Z")).occurred_at == (
            datetime(2026, 7, 12, 21, 0, tzinfo=UTC)
        )


class TestRequiringADataField:
    def test_require_returns_the_value(self) -> None:
        parsed = parse_envelope(COMMERCE_ORDER_CONFIRMED)

        assert parsed.require("toStatus") == "confirmed"

    def test_require_raises_a_permanent_error_naming_the_event_and_the_field(self) -> None:
        """A ``KeyError`` from inside a handler would be treated as retryable instead."""
        parsed = parse_envelope(COMMERCE_ORDER_CONFIRMED)

        with pytest.raises(MalformedEvent) as exc:
            parsed.require("deliveredAt")

        message = str(exc.value)
        assert "deliveredAt" in message
        assert parsed.event_id in message
        assert parsed.type in message
