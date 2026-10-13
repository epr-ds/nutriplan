"""COM-102: CreateOrderRequest/AddressRequest/PaymentMethodRequest match commerce.openapi.yaml.

Mirrors the OrderResponse drift-guard: the request models' field aliases must be a subset of the
documented properties and their required sets must match the contract exactly. Skips locally when
the spec is not mounted, but hard-fails under CI so a mis-wired gate can't pass silently.
"""

import os
import uuid
from datetime import date
from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic.alias_generators import to_camel

from app.api.schemas import AddressRequest, CreateOrderRequest, PaymentMethodRequest


def _aliases(model: type[BaseModel]) -> set[str]:
    return {field.alias or to_camel(name) for name, field in model.model_fields.items()}


def _required_aliases(model: type[BaseModel]) -> set[str]:
    return {
        field.alias or to_camel(name)
        for name, field in model.model_fields.items()
        if field.is_required()
    }


def test_create_order_request_parses_camelcase_and_maps_to_domain():
    request = CreateOrderRequest.model_validate(
        {
            "mealPlanId": str(uuid.uuid4()),
            "fulfillmentType": "grocery_delivery",
            "providerId": "freshbasket",
            "deliveryAddress": {
                "street": "Av. Reforma 100",
                "city": "CDMX",
                "state": "CDMX",
                "zipCode": "06600",
                "country": "MX",
                "apartment": "3B",
            },
            "deliveryDate": "2026-07-10",
            "deliveryTimeSlot": "12:00-13:00",
        }
    )
    assert isinstance(request.meal_plan_id, uuid.UUID)
    assert request.delivery_date == date(2026, 7, 10)
    address = request.delivery_address.to_domain()
    assert address.zip_code == "06600"
    assert address.apartment == "3B"


def _locate_spec() -> Path | None:
    override = os.environ.get("COMMERCE_OPENAPI_SPEC")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "commerce.openapi.yaml"
        if candidate.exists():
            return candidate
    return None


def test_request_schemas_conform_to_contract():
    spec_path = _locate_spec()
    if spec_path is None:
        if os.environ.get("CI"):
            raise RuntimeError("commerce.openapi.yaml not found under CI")
        pytest.skip("commerce.openapi.yaml not found (local run)")

    import yaml

    schemas = yaml.safe_load(spec_path.read_text(encoding="utf-8"))["components"]["schemas"]

    def documented(name: str) -> set[str]:
        return set(schemas[name].get("properties", {}).keys())

    def documented_required(name: str) -> set[str]:
        return set(schemas[name].get("required", []))

    for model, name in (
        (CreateOrderRequest, "CreateOrderRequest"),
        (AddressRequest, "AddressRequest"),
        (PaymentMethodRequest, "PaymentMethodRequest"),
    ):
        assert _aliases(model) <= documented(name), name
        assert _required_aliases(model) == documented_required(name), name
