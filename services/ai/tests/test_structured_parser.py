"""Tests for parsing + validating model output into a typed object (AIA-104, AC2)."""

import pytest
from pydantic import BaseModel

from app.structured.errors import OutputParsingError, OutputValidationError
from app.structured.parser import StructuredOutputParser


class Suggestion(BaseModel):
    title: str
    calories: int


_parser = StructuredOutputParser(Suggestion)


def test_parses_clean_json() -> None:
    result = _parser.parse('{"title": "Oatmeal", "calories": 300}')

    assert result == Suggestion(title="Oatmeal", calories=300)


def test_parses_json_inside_a_code_fence() -> None:
    text = '```json\n{"title": "Salad", "calories": 150}\n```'

    assert _parser.parse(text).title == "Salad"


def test_parses_json_embedded_in_prose() -> None:
    text = 'Sure! Here you go: {"title": "Soup", "calories": 200}. Enjoy.'

    assert _parser.parse(text).calories == 200


def test_invalid_json_raises_parsing_error() -> None:
    with pytest.raises(OutputParsingError):
        _parser.parse("not json at all")


def test_missing_field_raises_validation_error() -> None:
    with pytest.raises(OutputValidationError):
        _parser.parse('{"title": "X"}')


def test_wrong_type_raises_validation_error() -> None:
    with pytest.raises(OutputValidationError):
        _parser.parse('{"title": "X", "calories": "lots"}')


def test_validation_error_keeps_the_raw_output() -> None:
    raw = '{"title": "X"}'
    try:
        _parser.parse(raw)
    except OutputValidationError as exc:
        assert exc.raw_output == raw
    else:  # pragma: no cover - the call must raise
        raise AssertionError("expected OutputValidationError")


def test_response_format_reflects_the_model() -> None:
    fmt = _parser.response_format()

    assert fmt.name == "Suggestion"
    assert sorted(fmt.schema["required"]) == ["calories", "title"]
