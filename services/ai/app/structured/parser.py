"""Parsing + validating an LLM reply into a typed Pydantic instance (AIA-104, AC2).

The provider constraint asks for clean JSON, but a parser that only accepts perfectly
formatted output would be brittle, so this isolates the JSON value from common wrappers
(code fences, a sentence of prose) before validating it against the model. Any failure
becomes a typed :mod:`app.structured.errors` exception the completion loop can act on.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError

from app.llm.types import ResponseFormat
from app.structured.errors import OutputParsingError, OutputValidationError
from app.structured.schema import response_format_for


class StructuredOutputParser[T: BaseModel]:
    """Turns an LLM's text reply into a validated instance of a Pydantic model."""

    def __init__(self, model: type[T], *, name: str | None = None, strict: bool = True) -> None:
        self._model = model
        self._name = name or model.__name__
        self._strict = strict

    @property
    def model(self) -> type[T]:
        return self._model

    def response_format(self) -> ResponseFormat:
        """The provider constraint to attach to a request for this schema (AC1)."""
        return response_format_for(self._model, name=self._name, strict=self._strict)

    def parse(self, text: str) -> T:
        """Parse + validate ``text`` against the schema, or raise a typed error (AC2)."""
        payload = _extract_json(text)
        try:
            data = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise OutputParsingError(
                f"model output was not valid JSON: {exc}", raw_output=text
            ) from exc
        try:
            return self._model.model_validate(data)
        except ValidationError as exc:
            raise OutputValidationError(
                f"model output did not match {self._name}: {exc}", raw_output=text
            ) from exc


def _extract_json(text: str) -> str:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = _strip_code_fence(candidate)
    if candidate[:1] in ("{", "["):
        return candidate
    starts = [index for index in (candidate.find("{"), candidate.find("[")) if index != -1]
    ends = [index for index in (candidate.rfind("}"), candidate.rfind("]")) if index != -1]
    if starts and ends:
        start, end = min(starts), max(ends)
        if end > start:
            return candidate[start : end + 1]
    return candidate


def _strip_code_fence(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
