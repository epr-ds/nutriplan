"""COM-108: the RFC 7807 error model is documented in commerce.openapi.yaml.

The behavioural problem+json guarantees are asserted at the transport layer in
``test_error_model_api.py``; this suite pins the *published contract* so the documented error model
can't silently drift from what the service actually emits. It checks that:

* a reusable ``Problem`` schema exists (``type``/``title``/``status`` required), and
* reusable ``Unauthorized``/``NotFound``/``Conflict``/``UnprocessableEntity`` responses are declared
  as ``application/problem+json`` pointing at ``Problem``, and
* every order operation references the error responses it can actually return.

Skips locally when the spec is not mounted, but hard-fails under CI so a mis-wired gate can't pass
silently (same policy as the other commerce contract tests).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pytest

_PARAM = re.compile(r"\{[^}]+\}")

# Error responses each order op must document: (normalized path, method) -> {status: response-name}.
_EXPECTED = {
    ("/orders", "post"): {"401": "Unauthorized", "422": "UnprocessableEntity"},
    ("/orders", "get"): {"401": "Unauthorized", "422": "UnprocessableEntity"},
    ("/orders/{}", "get"): {"401": "Unauthorized", "404": "NotFound"},
    ("/orders/{}/cancel", "post"): {"401": "Unauthorized", "404": "NotFound", "409": "Conflict"},
}


def _normalize(path: str) -> str:
    return _PARAM.sub("{}", path)


def _locate_spec() -> Path | None:
    override = os.environ.get("COMMERCE_OPENAPI_SPEC")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "commerce.openapi.yaml"
        if candidate.exists():
            return candidate
    return None


def _load_spec() -> dict[str, Any]:
    spec_path = _locate_spec()
    if spec_path is None:
        if os.environ.get("CI"):
            raise RuntimeError("commerce.openapi.yaml not found under CI")
        pytest.skip("commerce.openapi.yaml not found (local run)")

    import yaml

    return yaml.safe_load(spec_path.read_text(encoding="utf-8"))


def _operation(spec: dict[str, Any], normalized: str, method: str) -> dict[str, Any] | None:
    for path, item in spec["paths"].items():
        if _normalize(path) == normalized and method in item:
            return item[method]
    return None


def _ref_name(node: dict[str, Any]) -> str | None:
    ref = node.get("$ref")
    return ref.split("/")[-1] if ref else None


def test_problem_schema_is_documented():
    spec = _load_spec()
    problem = spec["components"]["schemas"].get("Problem")
    assert problem is not None, "Problem schema is not documented in commerce.openapi.yaml"
    assert {"type", "title", "status"} <= set(problem.get("required", []))
    props = problem.get("properties", {})
    assert {"type", "title", "status"} <= set(props)


def test_reusable_error_responses_are_problem_json():
    spec = _load_spec()
    responses = spec["components"].get("responses", {})
    for name in ("Unauthorized", "NotFound", "Conflict", "UnprocessableEntity"):
        assert name in responses, f"{name} response is not documented"
        content = responses[name]["content"]
        assert "application/problem+json" in content, f"{name} is not application/problem+json"
        assert _ref_name(content["application/problem+json"]["schema"]) == "Problem"


@pytest.mark.parametrize("key,expected", _EXPECTED.items())
def test_order_operations_reference_error_responses(key: tuple[str, str], expected: dict[str, str]):
    normalized, method = key
    spec = _load_spec()
    operation = _operation(spec, normalized, method)
    assert operation is not None, f"{method.upper()} {normalized} is not documented"

    responses = operation["responses"]
    for status_code, response_name in expected.items():
        assert status_code in responses, f"{method.upper()} {normalized} is missing {status_code}"
        assert _ref_name(responses[status_code]) == response_name, (
            f"{method.upper()} {normalized} {status_code} should $ref {response_name}"
        )
