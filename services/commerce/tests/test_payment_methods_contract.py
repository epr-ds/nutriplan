"""COM-207 contract drift-guards for the saved-payment-methods surface.

The response projection's field names must be a subset of the properties documented for
``PaymentMethodResponse`` in ``contracts/commerce.openapi.yaml`` — and the stored ``token`` must be
absent from both the projection and the documented schema (it is a stored credential). The
save-request's fields must likewise be documented for ``SavePaymentMethodRequest``, and the three
routes must be published. The guard skips locally when the spec is not mounted, but hard-fails under
CI so a mis-wired gate can't pass silently.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from app.api.schemas import PaymentMethodResponse, SavePaymentMethodRequest
from app.domain.enums import PaymentMethodType
from app.domain.payment_method import SavedPaymentMethod


def _locate_spec() -> Path | None:
    override = os.environ.get("COMMERCE_OPENAPI_SPEC")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "commerce.openapi.yaml"
        if candidate.exists():
            return candidate
    return None


def _load() -> dict:
    spec_path = _locate_spec()
    if spec_path is None:
        if os.environ.get("CI"):
            raise RuntimeError("commerce.openapi.yaml not found under CI")
        pytest.skip("commerce.openapi.yaml not found (local run)")

    import yaml

    return yaml.safe_load(spec_path.read_text(encoding="utf-8"))


def _documented(spec: dict, name: str) -> set[str]:
    return set(spec["components"]["schemas"][name].get("properties", {}).keys())


def _method() -> SavedPaymentMethod:
    return SavedPaymentMethod(
        user_id=uuid.uuid4(),
        type=PaymentMethodType.CREDIT_CARD,
        token="tok_secret",
        brand="visa",
        last4="4242",
        exp_month=12,
        exp_year=2030,
    )


def test_response_projection_conforms_to_contract():
    spec = _load()
    data = PaymentMethodResponse.from_method(_method()).model_dump(by_alias=True)
    assert set(data.keys()) <= _documented(spec, "PaymentMethodResponse")


def test_contract_response_schema_omits_token():
    spec = _load()
    assert "token" not in _documented(spec, "PaymentMethodResponse")


def test_save_request_fields_conform_to_contract():
    spec = _load()
    body = SavePaymentMethodRequest(
        type=PaymentMethodType.CREDIT_CARD, token="tok_secret"
    ).model_dump(by_alias=True)
    assert set(body.keys()) <= _documented(spec, "SavePaymentMethodRequest")


def test_payment_methods_paths_documented():
    spec = _load()
    paths = spec["paths"]
    assert "get" in paths["/payment-methods"]
    assert "post" in paths["/payment-methods"]
    assert "delete" in paths["/payment-methods/{paymentMethodId}"]
