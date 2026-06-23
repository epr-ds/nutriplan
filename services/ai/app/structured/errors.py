"""Errors for turning an LLM reply into a validated, typed object (AIA-104).

Distinct from :mod:`app.llm.errors`, which covers *talking to* the provider: these
describe a response that arrived intact but whose *content* could not be made to fit the
expected schema. They are what the structured-completion loop catches to decide between
retrying and falling back, so they carry the offending output for logging.
"""

from __future__ import annotations


class StructuredOutputError(Exception):
    """The model's reply could not be turned into the expected typed object."""

    def __init__(self, message: str, *, raw_output: str | None = None) -> None:
        super().__init__(message)
        self.raw_output = raw_output


class OutputParsingError(StructuredOutputError):
    """The reply was not valid JSON (or no JSON value could be located in it)."""


class OutputValidationError(StructuredOutputError):
    """The reply parsed as JSON but did not satisfy the response schema."""
