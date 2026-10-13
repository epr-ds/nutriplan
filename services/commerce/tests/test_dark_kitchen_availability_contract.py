"""COM-301: ``GET /fulfillment/dark-kitchen/availability`` conforms to commerce.openapi.yaml.

Guards that the implemented operation stays faithful to the published contract: it returns an
``AvailabilityResponse`` on ``200`` and takes a required ``zipCode`` query parameter plus an
optional ``deliveryDate``. The contract side additionally checks the operation is authenticated and
that the ``AvailabilityResponse`` schema is exactly ``{available, zipCode, timeSlots}``, with the
app's projection a subset of it. Skips locally when the spec is not mounted, but hard-fails under CI
so a mis-wired gate can't pass silently.
"""

import os
from pathlib import Path
from typing import Any

import pytest

from app.api.schemas import AvailabilityResponse
from app.main import app

_PATH = "/fulfillment/dark-kitchen/availability"


def _get_operation(paths: dict[str, Any], path: str) -> dict[str, Any] | None:
    item = paths.get(path)
    return item.get("get") if item else None


def _response_schema_name(response: dict[str, Any]) -> str | None:
    schema = response.get("content", {}).get("application/json", {}).get("schema", {})
    ref = schema.get("$ref")
    return ref.split("/")[-1] if ref else None


def _query_params(operation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["name"]: p for p in operation.get("parameters", []) if p.get("in") == "query"}


def _impl_operation() -> dict[str, Any]:
    operation = _get_operation(app.openapi()["paths"], _PATH)
    assert operation is not None, f"GET {_PATH} is not exposed by the app"
    return operation


def test_app_returns_availability_response():
    assert _response_schema_name(_impl_operation()["responses"]["200"]) == "AvailabilityResponse"


def test_app_requires_zip_code_and_optional_delivery_date():
    params = _query_params(_impl_operation())
    assert params["zipCode"]["required"] is True
    assert "deliveryDate" in params
    assert params["deliveryDate"].get("required", False) is False


def test_app_projection_is_subset_of_documented_schema():
    documented = _spec_or_skip()["components"]["schemas"]["AvailabilityResponse"]["properties"]
    projected = AvailabilityResponse(available=True, zip_code="06600", time_slots=["x"]).model_dump(
        by_alias=True
    )
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


def test_contract_documents_authenticated_availability_operation():
    documented = _get_operation(_spec_or_skip()["paths"], _PATH)
    assert documented is not None, "getDarkKitchenAvailability is not documented in the contract"

    assert _response_schema_name(documented["responses"]["200"]) == "AvailabilityResponse"
    # Authenticated per the contract's security requirement.
    assert documented.get("security"), "the availability operation must require authentication"

    params = _query_params(documented)
    assert params["zipCode"]["required"] is True
    assert params["zipCode"]["schema"]["type"] == "string"
    assert params["deliveryDate"].get("required", False) is False


def test_contract_availability_response_shape():
    schema = _spec_or_skip()["components"]["schemas"]["AvailabilityResponse"]
    assert set(schema["properties"]) == {"available", "zipCode", "timeSlots"}
    assert schema["properties"]["available"]["type"] == "boolean"
    assert schema["properties"]["timeSlots"]["type"] == "array"
