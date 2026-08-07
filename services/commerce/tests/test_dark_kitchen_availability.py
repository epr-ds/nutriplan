"""COM-301: dark-kitchen availability — domain policy, use case, and HTTP endpoint.

Covers the pure coverage/schedule policy (:class:`DarkKitchenServiceArea`), the clock-injected
application service, and ``GET /fulfillment/dark-kitchen/availability`` end to end via dependency
overrides (auth stub + a fixed service area/clock), plus one test that exercises the real config
wiring. No database is involved — availability is a read-only computation.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_check_dark_kitchen_availability_service, get_token_verifier
from app.application.dark_kitchen_availability import CheckDarkKitchenAvailabilityService
from app.application.queries import DarkKitchenAvailabilityQuery
from app.core.principal import Principal
from app.domain.fulfillment import DarkKitchenAvailability, DarkKitchenServiceArea
from app.main import app
from tests.fakes import StubVerifier

GOOD_TOKEN = "good-token"
PRINCIPAL = Principal(user_id=str(uuid.uuid4()), email="a@b.com")

SLOTS = ("09:00-11:00", "11:00-13:00")
AREA = DarkKitchenServiceArea(served_zip_prefixes=("06", "01"), time_slots=SLOTS)
FIXED_TODAY = date(2026, 6, 1)

# ------------------------------------------------------------------------------- domain: coverage


def test_serves_returns_true_for_a_covered_prefix():
    assert AREA.serves("06600") is True


def test_serves_returns_false_outside_coverage():
    assert AREA.serves("99999") is False


def test_empty_prefixes_serve_nowhere():
    assert DarkKitchenServiceArea(served_zip_prefixes=(), time_slots=SLOTS).serves("06600") is False


def test_blank_prefix_does_not_match_everything():
    # A stray empty prefix must not turn coverage into "serve the whole world".
    area = DarkKitchenServiceArea(served_zip_prefixes=("",), time_slots=SLOTS)
    assert area.serves("06600") is False


def test_check_covered_zip_is_available_with_slots():
    result = AREA.check("06600")
    assert result == DarkKitchenAvailability(zip_code="06600", available=True, time_slots=SLOTS)


def test_check_uncovered_zip_is_unavailable_without_slots():
    result = AREA.check("99999")
    assert result.available is False
    assert result.time_slots == ()


# ------------------------------------------------------------------------- domain: delivery date


def test_past_delivery_date_is_not_serviceable():
    result = AREA.check("06600", delivery_date=date(2020, 1, 1), today=FIXED_TODAY)
    assert result.available is False
    assert result.time_slots == ()


def test_future_delivery_date_is_serviceable():
    result = AREA.check("06600", delivery_date=date(2999, 1, 1), today=FIXED_TODAY)
    assert result.available is True
    assert result.time_slots == SLOTS


def test_todays_delivery_date_is_serviceable():
    # The boundary date (== today) is not "past" and stays serviceable.
    result = AREA.check("06600", delivery_date=FIXED_TODAY, today=FIXED_TODAY)
    assert result.available is True


def test_delivery_date_ignored_without_a_today_reference():
    # The pure policy leaves the past-date rule to a caller that supplies "today".
    result = AREA.check("06600", delivery_date=date(2020, 1, 1))
    assert result.available is True


# ----------------------------------------------------------------------------- application service


def _service(clock_date: date = FIXED_TODAY) -> CheckDarkKitchenAvailabilityService:
    return CheckDarkKitchenAvailabilityService(AREA, clock=lambda: clock_date)


def test_service_resolves_today_from_the_injected_clock():
    result = _service().check(
        DarkKitchenAvailabilityQuery(zip_code="06600", delivery_date=date(2020, 1, 1))
    )
    assert result.available is False


def test_service_serves_a_covered_zip_without_a_date():
    result = _service().check(DarkKitchenAvailabilityQuery(zip_code="01000"))
    assert result.available is True
    assert result.time_slots == SLOTS


def test_service_default_clock_is_today():
    # Constructed with no clock, "now" is the real today; a far-future date stays serviceable.
    service = CheckDarkKitchenAvailabilityService(AREA)
    result = service.check(
        DarkKitchenAvailabilityQuery(zip_code="06600", delivery_date=date(2999, 1, 1))
    )
    assert result.available is True


# --------------------------------------------------------------------------------------- API layer


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    app.dependency_overrides.pop(get_check_dark_kitchen_availability_service, None)
    app.dependency_overrides.pop(get_token_verifier, None)


def _build(*, stub_service: bool = True) -> TestClient:
    if stub_service:
        app.dependency_overrides[get_check_dark_kitchen_availability_service] = _service
    app.dependency_overrides[get_token_verifier] = lambda: StubVerifier({GOOD_TOKEN: PRINCIPAL})
    return TestClient(app)


def _auth(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


_URL = "/fulfillment/dark-kitchen/availability"


def test_api_returns_available_for_a_covered_zip():
    client = _build()

    response = client.get(_URL, params={"zipCode": "06600"}, headers=_auth())

    assert response.status_code == 200
    data = response.json()
    assert data == {"available": True, "zipCode": "06600", "timeSlots": list(SLOTS)}


def test_api_returns_unavailable_for_an_uncovered_zip():
    client = _build()

    response = client.get(_URL, params={"zipCode": "99999"}, headers=_auth())

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert data["timeSlots"] == []


def test_api_past_delivery_date_is_unavailable():
    client = _build()

    response = client.get(
        _URL, params={"zipCode": "06600", "deliveryDate": "2020-01-01"}, headers=_auth()
    )

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_api_future_delivery_date_is_available():
    client = _build()

    response = client.get(
        _URL, params={"zipCode": "06600", "deliveryDate": "2999-01-01"}, headers=_auth()
    )

    assert response.status_code == 200
    assert response.json()["available"] is True


def test_api_requires_authentication():
    client = _build()

    assert client.get(_URL, params={"zipCode": "06600"}).status_code == 401


def test_api_rejects_unknown_token():
    client = _build()

    assert client.get(_URL, params={"zipCode": "06600"}, headers=_auth("nope")).status_code == 401


def test_api_rejects_non_numeric_zip():
    client = _build()

    assert client.get(_URL, params={"zipCode": "ABCDE"}, headers=_auth()).status_code == 422


def test_api_rejects_short_zip():
    client = _build()

    assert client.get(_URL, params={"zipCode": "123"}, headers=_auth()).status_code == 422


def test_api_requires_zip_code():
    client = _build()

    assert client.get(_URL, headers=_auth()).status_code == 422


def test_api_rejects_malformed_delivery_date():
    client = _build()

    response = client.get(
        _URL, params={"zipCode": "06600", "deliveryDate": "not-a-date"}, headers=_auth()
    )
    assert response.status_code == 422


def test_api_real_wiring_serves_a_default_config_zip():
    # No service override: exercises config -> deps -> domain for real (default coverage has "06").
    client = _build(stub_service=False)

    response = client.get(_URL, params={"zipCode": "06700"}, headers=_auth())

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert "09:00-11:00" in data["timeSlots"]
