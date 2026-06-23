"""Schema-constrained, validated structured outputs for the AI service (AIA-104).

Free-text completions can't be trusted to land on a response shape, so this package makes
schema conformance a property of the call rather than a hope: a Pydantic model both
constrains the provider (via :class:`~app.llm.types.ResponseFormat`) and validates the
reply, and :class:`StructuredCompletion` retries or falls back when validation fails. It
sits on top of :mod:`app.llm` and :mod:`app.prompts` and is consumed by the ``/ai/*``
endpoints from AIA-201.
"""

from app.structured.errors import (
    OutputParsingError,
    OutputValidationError,
    StructuredOutputError,
)
from app.structured.parser import StructuredOutputParser
from app.structured.schema import response_format_for, to_strict_json_schema
from app.structured.service import StructuredCompletion

__all__ = [
    "OutputParsingError",
    "OutputValidationError",
    "StructuredCompletion",
    "StructuredOutputError",
    "StructuredOutputParser",
    "response_format_for",
    "to_strict_json_schema",
]
