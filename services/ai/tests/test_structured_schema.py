"""Tests for deriving strict JSON schemas + response formats from models (AIA-104, AC1)."""

from pydantic import BaseModel

from app.structured.schema import response_format_for, to_strict_json_schema


def test_strict_sets_additional_properties_and_required() -> None:
    schema = {
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "string"}},
    }

    strict = to_strict_json_schema(schema)

    assert strict["additionalProperties"] is False
    assert sorted(strict["required"]) == ["a", "b"]


def test_strict_recurses_into_defs_and_arrays() -> None:
    schema = {
        "type": "object",
        "properties": {"items": {"type": "array", "items": {"$ref": "#/$defs/Item"}}},
        "$defs": {"Item": {"type": "object", "properties": {"n": {"type": "integer"}}}},
    }

    strict = to_strict_json_schema(schema)

    assert strict["required"] == ["items"]
    item = strict["$defs"]["Item"]
    assert item["additionalProperties"] is False
    assert item["required"] == ["n"]


def test_strict_does_not_mutate_input() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}

    to_strict_json_schema(schema)

    assert "additionalProperties" not in schema
    assert "required" not in schema


class _Meal(BaseModel):
    title: str
    calories: int


def test_response_format_for_uses_model_schema_and_name() -> None:
    fmt = response_format_for(_Meal)

    assert fmt.name == "_Meal"
    assert fmt.strict is True
    assert fmt.schema["additionalProperties"] is False
    assert sorted(fmt.schema["required"]) == ["calories", "title"]


def test_response_format_for_can_override_name_and_skip_strict() -> None:
    fmt = response_format_for(_Meal, name="Meal", strict=False)

    assert fmt.name == "Meal"
    assert fmt.strict is False
    assert "additionalProperties" not in fmt.schema
