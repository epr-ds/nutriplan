"""COM-401: ``GET /fulfillment/grocery/providers`` conforms to commerce.openapi.yaml.

Guards that the implemented operation stays faithful to the published contract: it returns a
``ProviderResponse[]`` on ``200``. The contract side additionally checks the operation is
authenticated and that the ``ProviderResponse`` schema is exactly ``{id, name, type, logoUrl,
estimatedDelivery}`` (``type`` enumerating ``dark_kitchen``/``grocery``), with the app's projection
a subset of it. Skips locally when the spec is not mounted, but hard-fails under CI so a mis-wired
gate can't pass silently.
"""

import os
from pathlib import Path
from typing import Any

import pytest

from app.api.schemas import ProviderResponse
from app.domain.grocery import GroceryProvider
from app.main import app

_PATH = "/fulfillment/grocery/providers"


def _get_operation(paths: dict[str, Any], path: str) -> dict[str, Any] | None:
    item = paths.get(path)
    return item.get("get") if item else None


def _array_item_schema_name(response: dict[str, Any]) -> str | None:
    schema = response.get("content", {}).get("application/json", {}).get("schema", {})
    if schema.get("type") != "array":
        return None
    ref = schema.get("items", {}).get("$ref")
    return ref.split("/")[-1] if ref else None


def _impl_operation() -> dict[str, Any]:
    operation = _get_operation(app.openapi()["paths"], _PATH)
    assert operation is not None, f"GET {_PATH} is not exposed by the app"
    return operation


def test_app_returns_array_of_provider_response():
    assert _array_item_schema_name(_impl_operation()["responses"]["200"]) == "ProviderResponse"


def test_app_projection_is_subset_of_documented_schema():
    documented = _spec_or_skip()["components"]["schemas"]["ProviderResponse"]["properties"]
    projected = ProviderResponse.from_domain(
        GroceryProvider(
            id="freshbasket",
            name="FreshBasket",
            logo_url="https://cdn.example.mx/freshbasket.png",
            estimated_delivery="Same day",
        )
    ).model_dump(by_alias=True)
    assert set(projected) <= set(documented)


def _locate_spec() -> Path | None:
    override = os.environ.get("COMMERCE_OPENAPI_SPEC")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "commerce.openapi.yaml"
        if candidate.exists():
            return candidate
    return None


def _spec_or_skip() -> dict[str, Any]:
    spec_path = _locate_spec()
    if spec_path is None:
        if os.environ.get("CI"):
            raise RuntimeError("commerce.openapi.yaml not found under CI")
        pytest.skip("commerce.openapi.yaml not found (local run)")

    import yaml

    return yaml.safe_load(spec_path.read_text(encoding="utf-8"))


def test_contract_documents_authenticated_providers_operation():
    documented = _get_operation(_spec_or_skip()["paths"], _PATH)
    assert documented is not None, "listGroceryProviders is not documented in the contract"

    assert _array_item_schema_name(documented["responses"]["200"]) == "ProviderResponse"
    # Authenticated per the contract's security requirement.
    assert documented.get("security"), "the providers operation must require authentication"


def test_contract_provider_response_shape():
    schema = _spec_or_skip()["components"]["schemas"]["ProviderResponse"]
    assert set(schema["properties"]) == {"id", "name", "type", "logoUrl", "estimatedDelivery"}
    assert set(schema["properties"]["type"]["enum"]) == {"dark_kitchen", "grocery"}
