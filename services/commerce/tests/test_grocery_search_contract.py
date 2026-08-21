"""COM-403: ``POST /fulfillment/grocery/search`` conforms to commerce.openapi.yaml.

Guards that the implemented operation stays faithful to the published contract: it accepts a
``GrocerySearchRequest`` body and returns a ``ProviderResponse[]`` on ``200``. The contract side
additionally checks the operation is authenticated and that ``GrocerySearchRequest`` requires
``items`` + ``zipCode`` (with an optional ``providers`` list). Skips locally when the spec is not
mounted, but hard-fails under CI so a mis-wired gate can't pass silently.
"""

import os
from pathlib import Path
from typing import Any

import pytest

from app.main import app

_PATH = "/fulfillment/grocery/search"


def _post_operation(paths: dict[str, Any], path: str) -> dict[str, Any] | None:
    item = paths.get(path)
    return item.get("post") if item else None


def _array_item_schema_name(response: dict[str, Any]) -> str | None:
    schema = response.get("content", {}).get("application/json", {}).get("schema", {})
    if schema.get("type") != "array":
        return None
    ref = schema.get("items", {}).get("$ref")
    return ref.split("/")[-1] if ref else None


def _request_schema_name(operation: dict[str, Any]) -> str | None:
    schema = (
        operation.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    ref = schema.get("$ref")
    return ref.split("/")[-1] if ref else None


def _impl_operation() -> dict[str, Any]:
    operation = _post_operation(app.openapi()["paths"], _PATH)
    assert operation is not None, f"POST {_PATH} is not exposed by the app"
    return operation


def test_app_returns_array_of_provider_response():
    assert _array_item_schema_name(_impl_operation()["responses"]["200"]) == "ProviderResponse"


def test_app_request_body_references_grocery_search_request():
    assert _request_schema_name(_impl_operation()) == "GrocerySearchRequest"


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


def test_contract_documents_authenticated_search_operation():
    documented = _post_operation(_spec_or_skip()["paths"], _PATH)
    assert documented is not None, "searchGroceryProducts is not documented in the contract"

    assert _array_item_schema_name(documented["responses"]["200"]) == "ProviderResponse"
    assert _request_schema_name(documented) == "GrocerySearchRequest"
    # Authenticated per the contract's security requirement.
    assert documented.get("security"), "the search operation must require authentication"


def test_contract_grocery_search_request_shape():
    schema = _spec_or_skip()["components"]["schemas"]["GrocerySearchRequest"]
    assert set(schema["required"]) == {"items", "zipCode"}
    # The app generates a $ref to GrocerySearchItemRequest for items; the contract inlines the item
    # object, so we only assert the top-level property set is a superset of the app's fields.
    assert {"items", "zipCode", "providers"} <= set(schema["properties"])
