"""The versioned schema registry and its compatibility verdicts (NTF-201, AC2).

The registry is the only thing standing between "the producer moved" and "a user gets the
wrong notification", so these tests are mostly about the *verdicts* rather than the lookup:
which drift is tolerable, which is not, and which is not even drift.
"""

from __future__ import annotations

import pytest

from app.events.envelope import EventEnvelope, parse_envelope
from app.events.registry import (
    ORDER_CONFIRMED,
    ORDER_CREATED,
    ORDER_EVENT_SCHEMAS,
    ORDER_EVENT_VERSION,
    ORDER_STATUS_CHANGED,
    Compatibility,
    EventSchema,
    EventSchemaRegistry,
    default_registry,
)
from tests.test_event_envelope import COMMERCE_ORDER_CONFIRMED, envelope


def parsed(**overrides: object) -> EventEnvelope:
    """A parsed envelope with ``overrides`` applied to the commerce sample."""
    return parse_envelope(envelope(**overrides))


class TestTheRegistryMatchesTheCommercePublisher:
    """Pins this build against ``services/commerce/app/events/envelope.py``.

    A registry that has drifted from the publisher is worse than no registry at all: it
    rejects valid traffic while reporting, in its own vocabulary, that everything is fine.
    """

    def test_the_three_order_event_types_are_registered(self) -> None:
        registry = default_registry()

        assert {schema.type for schema in registry.schemas} == {
            ORDER_CREATED,
            ORDER_CONFIRMED,
            ORDER_STATUS_CHANGED,
        }

    def test_they_are_registered_at_the_version_commerce_publishes(self) -> None:
        """``SCHEMA_VERSION = 1`` in the commerce envelope module."""
        registry = default_registry()

        for event_type in (ORDER_CREATED, ORDER_CONFIRMED, ORDER_STATUS_CHANGED):
            assert registry.versions_for(event_type) == (ORDER_EVENT_VERSION,)

    def test_order_created_requires_only_the_identifiers(self) -> None:
        """Commerce's ``_data`` sends just the two ids for a creation."""
        schema = default_registry().get(ORDER_CREATED, ORDER_EVENT_VERSION)

        assert schema is not None
        assert schema.required == frozenset({"orderId", "userId"})

    @pytest.mark.parametrize("event_type", [ORDER_CONFIRMED, ORDER_STATUS_CHANGED])
    def test_transition_events_also_require_both_ends_of_the_move(self, event_type: str) -> None:
        schema = default_registry().get(event_type, ORDER_EVENT_VERSION)

        assert schema is not None
        assert schema.required == frozenset({"orderId", "userId", "fromStatus", "toStatus"})

    def test_a_real_published_envelope_is_supported(self) -> None:
        verdict = default_registry().check(parse_envelope(COMMERCE_ORDER_CONFIRMED))

        assert verdict.compatibility is Compatibility.SUPPORTED
        assert verdict


class TestAnUnknownTypeIsNotAFailure:
    def test_an_unregistered_type_gets_the_unknown_verdict(self) -> None:
        verdict = default_registry().check(parsed(type="order.refunded"))

        assert verdict.compatibility is Compatibility.UNKNOWN_TYPE
        assert not verdict

    def test_an_unknown_type_is_not_worth_parking(self) -> None:
        """A dead-letter queue that alarms on ordinary traffic is one nobody reads."""
        verdict = default_registry().check(parsed(type="loyalty.points_awarded"))

        assert not verdict.compatibility.should_dead_letter

    def test_the_reason_names_the_type(self) -> None:
        verdict = default_registry().check(parsed(type="order.refunded"))

        assert "order.refunded" in verdict.reason


class TestAnUnknownVersionIsParkedNotGuessed:
    def test_a_higher_version_is_unsupported_even_when_the_fields_look_familiar(self) -> None:
        """The bump *is* the signal that the meaning changed; the shape says nothing."""
        verdict = default_registry().check(parsed(schemaVersion=2))

        assert verdict.compatibility is Compatibility.UNSUPPORTED_VERSION
        assert not verdict

    def test_an_unsupported_version_is_parked_for_a_later_build(self) -> None:
        """This is the one permanent failure that a deploy actually fixes."""
        verdict = default_registry().check(parsed(schemaVersion=7))

        assert verdict.compatibility.should_dead_letter

    def test_the_reason_says_what_arrived_and_what_is_understood(self) -> None:
        verdict = default_registry().check(parsed(schemaVersion=2))

        assert "v2" in verdict.reason
        assert "v1" in verdict.reason
        assert ORDER_CONFIRMED in verdict.reason

    def test_a_version_below_the_registered_one_is_also_unsupported(self) -> None:
        """Dropping support for an old version must be a refusal, not a silent misread."""
        registry = EventSchemaRegistry(
            [EventSchema(ORDER_CONFIRMED, 2, frozenset({"orderId", "userId"}))]
        )

        assert registry.check(parsed(schemaVersion=1)).compatibility is (
            Compatibility.UNSUPPORTED_VERSION
        )


class TestMissingRequiredFields:
    @pytest.mark.parametrize("field", ["orderId", "userId", "fromStatus", "toStatus"])
    def test_a_payload_missing_a_required_field_is_incompatible(self, field: str) -> None:
        data = {k: v for k, v in COMMERCE_ORDER_CONFIRMED["data"].items() if k != field}  # type: ignore[union-attr]

        verdict = default_registry().check(parsed(data=data))

        assert verdict.compatibility is Compatibility.MISSING_FIELDS
        assert verdict.missing == (field,)

    def test_every_missing_field_is_reported_together(self) -> None:
        verdict = default_registry().check(parsed(data={"orderId": "o-1"}))

        assert verdict.missing == ("fromStatus", "toStatus", "userId")
        assert "fromStatus, toStatus, userId" in verdict.reason

    def test_a_broken_producer_is_parked(self) -> None:
        verdict = default_registry().check(parsed(data={}))

        assert verdict.compatibility.should_dead_letter

    def test_a_present_but_empty_value_still_counts_as_present(self) -> None:
        """The registry checks the *shape*; whether a value makes sense is the handler's call."""
        data = {**COMMERCE_ORDER_CONFIRMED["data"], "toStatus": ""}  # type: ignore[dict-item]

        assert default_registry().check(parsed(data=data)).compatibility is (
            Compatibility.SUPPORTED
        )


class TestRegistration:
    def test_registering_the_same_type_and_version_twice_is_refused(self) -> None:
        """An import-order accident must not silently decide which definition wins."""
        registry = EventSchemaRegistry([EventSchema(ORDER_CREATED, 1)])

        with pytest.raises(ValueError, match="already registered"):
            registry.register(EventSchema(ORDER_CREATED, 1, frozenset({"orderId"})))

    def test_two_versions_of_one_type_coexist(self) -> None:
        """Which is how a consumer supports a transition rather than a cutover."""
        registry = EventSchemaRegistry(
            [EventSchema(ORDER_CREATED, 1), EventSchema(ORDER_CREATED, 2)]
        )

        assert registry.versions_for(ORDER_CREATED) == (1, 2)
        assert registry.check(parsed(type=ORDER_CREATED, schemaVersion=2))

    def test_an_unknown_type_has_no_versions(self) -> None:
        assert default_registry().versions_for("order.refunded") == ()

    def test_the_default_registry_is_not_shared_between_callers(self) -> None:
        """A test registering an extra schema must not leak it into the next one."""
        first = default_registry()
        first.register(EventSchema("order.refunded", 1))

        assert not default_registry().knows_type("order.refunded")

    def test_the_seeded_schemas_are_the_default_registry_contents(self) -> None:
        assert default_registry().schemas == tuple(
            sorted(ORDER_EVENT_SCHEMAS, key=lambda schema: schema.key)
        )
