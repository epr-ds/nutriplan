"""COM-208: the refund-on-cancellation contract addenda match commerce.openapi.yaml.

Guards that ``cancelOrder`` documents the optional ``CancelOrderRequest`` body and a ``422``, that
``OrderResponse`` carries a ``refund`` block, and that the ``RefundResponse`` and
``CancelOrderRequest`` schemas are published. Also checks the app exposes the cancel body as
*optional* (an empty POST must still cancel). Skips locally when the spec is not mounted; hard-fails
under CI so a mis-wired gate can't pass silently.
"""

import os
import re
from pathlib import Path
from typing import Any

import pytest

from app.main import app

_PARAM = re.compile(r"\{[^}]+\}")


def _normalize(path: str) -> str:
    return _PARAM.sub("{}", path)


def _operation(paths: dict[str, Any], normalized: str, method: str) -> dict[str, Any] | None:
    for path, item in paths.items():
        if _normalize(path) == normalized and method in item:
            return item[method]
    return None


def test_app_cancel_body_is_optional():
    operation = _operation(app.openapi()["paths"], "/orders/{}/cancel", "post")
    assert operation is not None, "POST /orders/{orderId}/cancel is not exposed by the app"
    # An absent body must be allowed so a plain (no-refund) cancel keeps working.
    assert operation.get("requestBody", {}).get("required", False) is False


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


def test_contract_cancel_documents_optional_refund_body_and_422():
    spec = _spec()
    documented = _operation(spec["paths"], "/orders/{}/cancel", "post")
    assert documented is not None, "cancelOrder is not documented in commerce.openapi.yaml"

    body = documented.get("requestBody", {})
    assert body.get("required", False) is False
    schema = body["content"]["application/json"]["schema"]
    assert schema["$ref"].split("/")[-1] == "CancelOrderRequest"
    assert "422" in documented["responses"]


def test_contract_order_response_has_refund():
    schemas = _spec()["components"]["schemas"]
    refund = schemas["OrderResponse"]["properties"]["refund"]
    assert refund["$ref"].split("/")[-1] == "RefundResponse"


def test_contract_publishes_refund_schemas():
    schemas = _spec()["components"]["schemas"]

    cancel_req = schemas["CancelOrderRequest"]["properties"]
    assert cancel_req["refundAmount"]["type"] == "number"

    refund = schemas["RefundResponse"]["properties"]
    assert set(refund) == {"refundId", "status", "amount", "provider"}
    assert set(refund["status"]["enum"]) == {"full", "partial"}
    assert refund["amount"]["$ref"].split("/")[-1] == "MoneyResponse"
