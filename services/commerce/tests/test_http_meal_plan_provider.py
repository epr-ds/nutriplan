"""COM-102 unit tests for the Dietary HTTP meal-plan adapter (no live Dietary).

An ``httpx.MockTransport`` stands in for the network so the adapter's request shape (path + token
relay) and response mapping (200 -> snapshot, 404 -> None, other/transport error -> unavailable)
are exercised deterministically.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import httpx
import pytest

from app.adapters.http_meal_plan_provider import HttpMealPlanProvider
from app.domain.errors import MealPlanUnavailableError

BASE_URL = "http://dietary:8082"
PLAN_ID = str(uuid.uuid4())
TOKEN = "caller-token"

_PLAN_BODY = {
    "id": PLAN_ID,
    "name": "Cutting",
    "startDate": "2026-07-01",
    "endDate": "2026-07-07",
    "dailyCalorieTarget": 2000,
    "status": "active",
    "meals": [
        {"id": "m1", "mealType": "breakfast", "servings": 1, "recipe": None},
        {"id": "m2", "mealType": "lunch", "servings": 2.5, "recipe": {"id": "r9", "name": "Tacos"}},
    ],
}


def _provider(handler) -> HttpMealPlanProvider:
    return HttpMealPlanProvider(base_url=BASE_URL, transport=httpx.MockTransport(handler))


def test_fetch_maps_plan_to_snapshot_and_relays_token():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json=_PLAN_BODY)

    snapshot = _provider(handler).fetch(PLAN_ID, bearer_token=TOKEN)

    assert captured["path"] == f"/meal-plans/{PLAN_ID}"
    assert captured["auth"] == f"Bearer {TOKEN}"
    assert snapshot is not None
    assert snapshot.plan_id == PLAN_ID
    assert [m.meal_type for m in snapshot.meals] == ["breakfast", "lunch"]
    assert snapshot.meals[0].recipe_name is None
    assert snapshot.meals[1].recipe_name == "Tacos"
    assert snapshot.meals[1].servings == Decimal("2.5")


def test_fetch_returns_none_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"title": "Not Found"})

    assert _provider(handler).fetch(PLAN_ID, bearer_token=TOKEN) is None


@pytest.mark.parametrize("status_code", [401, 403, 500, 502, 503])
def test_fetch_raises_unavailable_on_unexpected_status(status_code: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={})

    with pytest.raises(MealPlanUnavailableError):
        _provider(handler).fetch(PLAN_ID, bearer_token=TOKEN)


def test_fetch_raises_unavailable_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(MealPlanUnavailableError):
        _provider(handler).fetch(PLAN_ID, bearer_token=TOKEN)


def test_fetch_tolerates_missing_meals_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": PLAN_ID, "status": "active"})

    snapshot = _provider(handler).fetch(PLAN_ID, bearer_token=TOKEN)
    assert snapshot is not None
    assert snapshot.meals == []
