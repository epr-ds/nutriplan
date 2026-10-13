"""COM-302: dark-kitchen capacity & time-slot model.

Extends COM-301 availability so a delivery window is only offered while it has remaining capacity
for the requested day. Covers the pure slot math (:class:`SlotAvailability`), the capacity-aware
:meth:`DarkKitchenServiceArea.check`, the application service reading booking counts from the
:class:`SlotInventory` port (only when a date is given), and the HTTP endpoint dropping a full
window and reporting an area whose every window is booked out as unavailable. No database is
involved — booking counts are supplied through the port, whose persistent writer arrives with slot
reservation (COM-304).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_check_dark_kitchen_availability_service,
    get_slot_inventory,
    get_token_verifier,
)
from app.application.dark_kitchen_availability import CheckDarkKitchenAvailabilityService
from app.application.queries import DarkKitchenAvailabilityQuery
from app.core.principal import Principal
from app.domain.fulfillment import DarkKitchenServiceArea, SlotAvailability
from app.main import app
from tests.fakes import StubVerifier

GOOD_TOKEN = "good-token"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")

SLOTS = ("09:00-11:00", "11:00-13:00", "13:00-15:00")
FIXED_TODAY = date(2026, 6, 1)
FUTURE = date(2026, 6, 10)
AREA = DarkKitchenServiceArea(served_zip_prefixes=("06", "01"), time_slots=SLOTS, slot_capacity=2)


class _StubInventory:
    """A :class:`SlotInventory` returning canned booking counts, recording each lookup."""

    def __init__(self, counts: Mapping[str, int] | None = None) -> None:
        self._counts = dict(counts or {})
        self.calls: list[tuple[str, date]] = []

    def booked_counts(self, zip_code: str, delivery_date: date) -> Mapping[str, int]:
        self.calls.append((zip_code, delivery_date))
        return self._counts


# ------------------------------------------------------------------------------ domain: slot math


def test_slot_remaining_is_capacity_minus_booked():
    assert SlotAvailability(slot="09:00-11:00", capacity=5, booked=2).remaining == 3


def test_slot_with_headroom_is_bookable():
    assert SlotAvailability(slot="09:00-11:00", capacity=5, booked=4).is_bookable is True


def test_full_slot_is_not_bookable():
    slot = SlotAvailability(slot="09:00-11:00", capacity=5, booked=5)
    assert slot.remaining == 0
    assert slot.is_bookable is False


def test_overbooked_slot_never_reports_negative_remaining():
    slot = SlotAvailability(slot="09:00-11:00", capacity=5, booked=9)
    assert slot.remaining == 0
    assert slot.is_bookable is False


def test_negative_booked_is_treated_as_zero():
    assert SlotAvailability(slot="09:00-11:00", capacity=5, booked=-3).remaining == 5


def test_unbooked_slot_reports_full_capacity():
    assert SlotAvailability(slot="09:00-11:00", capacity=5).remaining == 5


# ------------------------------------------------------------------- domain: capacity-aware check


def test_check_without_bookings_offers_every_window():
    result = AREA.check("06600")
    assert result.available is True
    assert result.time_slots == SLOTS


def test_check_drops_a_window_that_is_full():
    result = AREA.check("06600", booked={"09:00-11:00": 2})
    assert result.available is True
    assert result.time_slots == ("11:00-13:00", "13:00-15:00")


def test_check_keeps_a_window_with_partial_bookings():
    # capacity 2, one booked -> one seat left -> still offered.
    result = AREA.check("06600", booked={"09:00-11:00": 1})
    assert result.time_slots == SLOTS


def test_check_area_fully_booked_is_unavailable():
    booked = dict.fromkeys(SLOTS, 2)
    result = AREA.check("06600", booked=booked)
    assert result.available is False
    assert result.time_slots == ()


def test_unknown_window_in_booked_counts_is_ignored():
    result = AREA.check("06600", booked={"99:99-99:99": 99})
    assert result.time_slots == SLOTS


def test_uncovered_zip_ignores_capacity():
    result = AREA.check("99999", booked={"09:00-11:00": 0})
    assert result.available is False
    assert result.time_slots == ()


def test_past_date_stays_unavailable_regardless_of_capacity():
    result = AREA.check("06600", delivery_date=date(2020, 1, 1), today=FIXED_TODAY, booked={})
    assert result.available is False


def test_slot_availabilities_reports_remaining_per_window():
    rows = AREA.slot_availabilities(booked={"09:00-11:00": 2, "11:00-13:00": 1})
    remaining = {row.slot: row.remaining for row in rows}
    assert remaining == {"09:00-11:00": 0, "11:00-13:00": 1, "13:00-15:00": 2}


# ---------------------------------------------------------------------------- application service


def _service(inventory: _StubInventory) -> CheckDarkKitchenAvailabilityService:
    return CheckDarkKitchenAvailabilityService(AREA, inventory=inventory, clock=lambda: FIXED_TODAY)


def test_service_subtracts_booked_counts_for_a_dated_query():
    inventory = _StubInventory({"09:00-11:00": 2})
    result = _service(inventory).check(
        DarkKitchenAvailabilityQuery(zip_code="06600", delivery_date=FUTURE)
    )
    assert result.time_slots == ("11:00-13:00", "13:00-15:00")
    assert inventory.calls == [("06600", FUTURE)]


def test_service_does_not_consult_inventory_without_a_date():
    inventory = _StubInventory(dict.fromkeys(SLOTS, 2))
    result = _service(inventory).check(DarkKitchenAvailabilityQuery(zip_code="06600"))
    # No date -> capacity is not priced, every window is offered and the port is never touched.
    assert result.time_slots == SLOTS
    assert inventory.calls == []


def test_service_reports_unavailable_when_every_window_is_booked_out():
    inventory = _StubInventory(dict.fromkeys(SLOTS, 2))
    result = _service(inventory).check(
        DarkKitchenAvailabilityQuery(zip_code="06600", delivery_date=FUTURE)
    )
    assert result.available is False
    assert result.time_slots == ()


def test_service_defaults_to_empty_inventory():
    # Constructed with no inventory, a dated query still sees every window (nothing booked).
    service = CheckDarkKitchenAvailabilityService(AREA, clock=lambda: FIXED_TODAY)
    result = service.check(DarkKitchenAvailabilityQuery(zip_code="06600", delivery_date=FUTURE))
    assert result.time_slots == SLOTS


# ------------------------------------------------------------------------------------- API layer


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    app.dependency_overrides.pop(get_check_dark_kitchen_availability_service, None)
    app.dependency_overrides.pop(get_slot_inventory, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _build(inventory: _StubInventory) -> TestClient:
    app.dependency_overrides[get_check_dark_kitchen_availability_service] = lambda: _service(
        inventory
    )
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app)


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


_URL = "/fulfillment/dark-kitchen/availability"


def test_api_omits_a_fully_booked_window():
    client = _build(_StubInventory({"09:00-11:00": 2}))

    response = client.get(
        _URL, params={"zipCode": "06600", "deliveryDate": FUTURE.isoformat()}, headers=_auth()
    )

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["timeSlots"] == ["11:00-13:00", "13:00-15:00"]


def test_api_area_booked_out_is_unavailable():
    client = _build(_StubInventory(dict.fromkeys(SLOTS, 2)))

    response = client.get(
        _URL, params={"zipCode": "06600", "deliveryDate": FUTURE.isoformat()}, headers=_auth()
    )

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert data["timeSlots"] == []


def test_api_without_date_shows_full_schedule():
    client = _build(_StubInventory(dict.fromkeys(SLOTS, 2)))

    response = client.get(_URL, params={"zipCode": "06600"}, headers=_auth())

    assert response.status_code == 200
    assert response.json()["timeSlots"] == list(SLOTS)


def test_api_real_wiring_uses_empty_inventory_and_configured_capacity():
    # No overrides beyond auth: config -> deps -> EmptySlotInventory -> full default schedule.
    # A far-future date keeps the request serviceable regardless of the real clock.
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    client = TestClient(app)

    response = client.get(
        _URL, params={"zipCode": "06700", "deliveryDate": "2999-01-01"}, headers=_auth()
    )

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert "09:00-11:00" in data["timeSlots"]
