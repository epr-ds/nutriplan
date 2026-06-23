"""Deriving a provider response-format from a Pydantic model (AIA-104, AC1).

The service's response shapes are Pydantic models (the same models FastAPI turns into the
OpenAPI schema), so a model is the single source of truth for both the constraint sent to
the provider and the validation applied to its reply. ``response_format_for`` turns a
model into a :class:`~app.llm.types.ResponseFormat`; ``to_strict_json_schema`` tightens a
schema to the shape strict structured-output modes require.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from app.llm.types import ResponseFormat


def to_strict_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep copy of ``schema`` tightened for strict structured outputs.

    Strict mode (e.g. OpenAI) requires every object to forbid additional properties and
    to list all of its properties as ``required``. This walks the whole schema -- nested
    objects, array ``items``, ``$defs``, and combinators such as ``anyOf`` -- applying
    both rules, and never mutates the input.
    """
    return _strict(schema)


def _strict(node: Any) -> Any:
    if isinstance(node, Mapping):
        result: dict[str, Any] = {key: _strict(value) for key, value in node.items()}
        properties = result.get("properties")
        if result.get("type") == "object" and isinstance(properties, dict):
            result["additionalProperties"] = False
            result["required"] = list(properties.keys())
        return result
    if isinstance(node, list):
        return [_strict(item) for item in node]
    return node


def response_format_for(
    model: type[BaseModel], *, name: str | None = None, strict: bool = True
) -> ResponseFormat:
    """Build a :class:`ResponseFormat` from a Pydantic model's JSON schema."""
    schema: Mapping[str, Any] = model.model_json_schema()
    if strict:
        schema = to_strict_json_schema(schema)
    return ResponseFormat(name=name or model.__name__, schema=schema, strict=strict)
