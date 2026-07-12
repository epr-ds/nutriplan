"""COM-104: ``GET /orders`` query parameters conform to commerce.openapi.yaml (``listOrders``).

Guards against query-param drift both ways — the implemented parameters must exactly match the
documented ones. Skips locally when the spec is not mounted, but hard-fails under CI so a mis-wired
gate can't pass silently.
"""

import os
from pathlib import Path

import pytest

from app.main import app


def _impl_query_params() -> set[str]:
    schema = app.openapi()
    params = schema["paths"]["/orders"]["get"].get("parameters", [])
    return {p["name"] for p in params if p["in"] == "query"}


def test_list_orders_exposes_expected_query_params():
    assert _impl_query_params() == {"status", "fromDate", "page", "limit"}


def _locate_spec() -> Path | None:
    override = os.environ.get("COMMERCE_OPENAPI_SPEC")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "commerce.openapi.yaml"
        if candidate.exists():
            return candidate
    return None


def test_query_params_conform_to_contract():
    spec_path = _locate_spec()
    if spec_path is None:
        if os.environ.get("CI"):
            raise RuntimeError("commerce.openapi.yaml not found under CI")
        pytest.skip("commerce.openapi.yaml not found (local run)")

    import yaml

    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    documented = {
        p["name"]
        for p in spec["paths"]["/orders"]["get"].get("parameters", [])
        if p["in"] == "query"
    }
    assert _impl_query_params() == documented
