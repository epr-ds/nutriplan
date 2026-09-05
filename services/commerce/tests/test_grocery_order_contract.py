"""COM-408: the grocery-order surface conforms to commerce.openapi.yaml (AC3, the addendum).

Guards that the implemented grocery placement/status surface stays faithful to the published
contract addendum: ``POST /orders/{orderId}/grocery/sync`` returns an ``OrderResponse`` on ``200``
and documents its ``401``/``404``/``409``/``503`` paths, and an order projects the grocery placement
through a ``GroceryOrderResponse`` whose ``status`` enum is exactly the canonical
:class:`~app.domain.grocery_catalog.GroceryOrderStatus` vocabulary -- so a provider status can never
reach a client except through the anti-corruption layer's translation. Skips locally when the spec
is not mounted, but hard-fails under CI so a mis-wired gate can't pass silently.
"""

import os
from pathlib import Path
from typing import Any

import pytest

from app.domain.grocery_catalog import GroceryOrderStatus
from app.main import app

SYNC_PATH = "/orders/{orderId}/grocery/sync"
IMPL_SYNC_PATH = "/orders/{order_id}/grocery/sync"


def _operation(paths: dict[str, Any], path: str, method: str) -> dict[str, Any] | None:
    item = paths.get(path)
    return item.get(method) if item else None


def _response_schema_name(response: dict[str, Any]) -> str | None:
    schema = response.get("content", {}).get("application/json", {}).get("schema", {})
    ref = schema.get("$ref")
    return ref.split("/")[-1] if ref else None


def _impl_sync() -> dict[str, Any]:
    operation = _operation(app.openapi()["paths"], IMPL_SYNC_PATH, "post")
    assert operation is not None, f"POST {IMPL_SYNC_PATH} is not exposed by the app"
    return operation


def test_sync_returns_the_order_schema():
    assert _response_schema_name(_impl_sync()["responses"]["200"]) == "OrderResponse"


def test_the_app_projects_the_grocery_order_block():
    schemas = app.openapi()["components"]["schemas"]
    assert "groceryOrder" in schemas["OrderResponse"]["properties"]
    assert "GroceryOrderResponse" in schemas


def _locate_spec() -> Path | None:
    override = os.environ.get("COMMERCE_OPENAPI_SPEC")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "commerce.openapi.yaml"
        if candidate.exists():
            return candidate
    return None


def _spec() -> dict[str, Any]:
    spec_path = _locate_spec()
    if spec_path is None:
        if os.environ.get("CI"):
            raise RuntimeError("commerce.openapi.yaml not found under CI")
        pytest.skip("commerce.openapi.yaml not found (local run)")

    import yaml

    return yaml.safe_load(spec_path.read_text(encoding="utf-8"))


def test_sync_conforms_to_contract():
    documented = _operation(_spec()["paths"], SYNC_PATH, "post")
    assert documented is not None, "syncGroceryOrder is not documented in commerce.openapi.yaml"

    assert {"200", "401", "404", "409", "503"} <= set(documented["responses"])
    assert _response_schema_name(documented["responses"]["200"]) == "OrderResponse"
    # The implementation returns the same success payload the contract promises.
    assert _response_schema_name(_impl_sync()["responses"]["200"]) == "OrderResponse"


def test_grocery_order_response_is_documented():
    schemas = _spec()["components"]["schemas"]
    assert "GroceryOrderResponse" in schemas
    documented = schemas["GroceryOrderResponse"]["properties"]
    assert set(documented) == {"providerId", "externalOrderId", "status"}
    # Only the canonical (translated) vocabulary is ever published.
    assert set(documented["status"]["enum"]) == {status.value for status in GroceryOrderStatus}


def test_the_order_response_carries_the_grocery_order():
    schemas = _spec()["components"]["schemas"]
    grocery_order = schemas["OrderResponse"]["properties"].get("groceryOrder")
    assert grocery_order == {"$ref": "#/components/schemas/GroceryOrderResponse"}


def test_the_service_unavailable_response_is_reusable():
    responses = _spec()["components"]["responses"]
    assert "ServiceUnavailable" in responses
    assert "application/problem+json" in responses["ServiceUnavailable"]["content"]
