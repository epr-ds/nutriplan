"""COM-206: ``POST /webhooks/payments`` conforms to commerce.openapi.yaml (``paymentWebhook``).

Guards that the implemented webhook operation stays faithful to the published contract addendum: it
returns a ``PaymentWebhookAck`` on ``200``, accepts a ``PaymentWebhookEvent`` body, is authenticated
by signature (so it carries no bearer security requirement), and documents the ``400`` (bad
signature) / ``404`` (unknown order) / ``409`` (contradictory settlement) paths. Skips locally when
the spec is not mounted, but hard-fails under CI so a mis-wired gate can't pass silently.
"""

import os
from pathlib import Path
from typing import Any

import pytest

from app.main import app


def _operation(paths: dict[str, Any], path: str, method: str) -> dict[str, Any] | None:
    item = paths.get(path)
    return item.get(method) if item else None


def _response_schema_name(response: dict[str, Any]) -> str | None:
    schema = response.get("content", {}).get("application/json", {}).get("schema", {})
    ref = schema.get("$ref")
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


def _impl_webhook() -> dict[str, Any]:
    operation = _operation(app.openapi()["paths"], "/webhooks/payments", "post")
    assert operation is not None, "POST /webhooks/payments is not exposed by the app"
    return operation


def test_webhook_returns_ack_schema():
    assert _response_schema_name(_impl_webhook()["responses"]["200"]) == "PaymentWebhookAck"


def test_webhook_carries_no_bearer_security_requirement():
    # The webhook is authenticated by its signature header, not a user bearer token.
    assert not _impl_webhook().get("security")


def _locate_spec() -> Path | None:
    override = os.environ.get("COMMERCE_OPENAPI_SPEC")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "commerce.openapi.yaml"
        if candidate.exists():
            return candidate
    return None


def test_webhook_conforms_to_contract():
    spec_path = _locate_spec()
    if spec_path is None:
        if os.environ.get("CI"):
            raise RuntimeError("commerce.openapi.yaml not found under CI")
        pytest.skip("commerce.openapi.yaml not found (local run)")

    import yaml

    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    documented = _operation(spec["paths"], "/webhooks/payments", "post")
    assert documented is not None, "paymentWebhook is not documented in commerce.openapi.yaml"

    assert {"200", "400", "404", "409"} <= set(documented["responses"])
    assert _response_schema_name(documented["responses"]["200"]) == "PaymentWebhookAck"
    assert _request_schema_name(documented) == "PaymentWebhookEvent"

    schemas = spec["components"]["schemas"]
    assert "PaymentWebhookEvent" in schemas
    assert "PaymentWebhookAck" in schemas
    # The implementation returns the same success payload the contract promises.
    assert _response_schema_name(_impl_webhook()["responses"]["200"]) == "PaymentWebhookAck"
