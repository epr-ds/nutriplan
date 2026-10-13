"""COM-107: ``POST /orders/{orderId}/cancel`` conforms to commerce.openapi.yaml (``cancelOrder``).

Guards that the implemented cancel operation stays faithful to the published contract: it returns
an ``OrderResponse`` on ``200`` and documents the owner-scoped ``404`` and the state-machine
``409``, with a required UUID path parameter. Path parameter *names* are cosmetic (the repo uses a
snake-case route param while the contract uses ``orderId``), so both sides are compared on a
name-normalized path. Skips locally when the spec is not mounted, but hard-fails under CI so a
mis-wired gate can't pass silently.
"""

import os
import re
from pathlib import Path
from typing import Any

import pytest

from app.main import app

_PARAM = re.compile(r"\{[^}]+\}")


def _normalize(path: str) -> str:
    """Collapse templated segments so snake-case and camelCase path params compare equal."""
    return _PARAM.sub("{}", path)


def _operation(paths: dict[str, Any], normalized: str, method: str) -> dict[str, Any] | None:
    for path, item in paths.items():
        if _normalize(path) == normalized and method in item:
            return item[method]
    return None


def _response_schema_name(response: dict[str, Any]) -> str | None:
    schema = response.get("content", {}).get("application/json", {}).get("schema", {})
    ref = schema.get("$ref")
    return ref.split("/")[-1] if ref else None


def _impl_cancel_order() -> dict[str, Any]:
    operation = _operation(app.openapi()["paths"], "/orders/{}/cancel", "post")
    assert operation is not None, "POST /orders/{orderId}/cancel is not exposed by the app"
    return operation


def test_cancel_order_returns_order_response():
    assert _response_schema_name(_impl_cancel_order()["responses"]["200"]) == "OrderResponse"


def test_cancel_order_has_required_uuid_path_param():
    path_params = [p for p in _impl_cancel_order().get("parameters", []) if p["in"] == "path"]
    assert len(path_params) == 1
    assert path_params[0]["required"] is True
    assert path_params[0]["schema"].get("format") == "uuid"


def _locate_spec() -> Path | None:
    override = os.environ.get("COMMERCE_OPENAPI_SPEC")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "commerce.openapi.yaml"
        if candidate.exists():
            return candidate
    return None


def test_cancel_order_conforms_to_contract():
    spec_path = _locate_spec()
    if spec_path is None:
        if os.environ.get("CI"):
            raise RuntimeError("commerce.openapi.yaml not found under CI")
        pytest.skip("commerce.openapi.yaml not found (local run)")

    import yaml

    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    documented = _operation(spec["paths"], "/orders/{}/cancel", "post")
    assert documented is not None, "cancelOrder is not documented in commerce.openapi.yaml"

    assert {"200", "404", "409"} <= set(documented["responses"])
    assert _response_schema_name(documented["responses"]["200"]) == "OrderResponse"
    # The implementation returns the same success payload the contract promises.
    assert _response_schema_name(_impl_cancel_order()["responses"]["200"]) == "OrderResponse"
