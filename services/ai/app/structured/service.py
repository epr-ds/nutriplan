"""Constrain -> call -> parse -> validate, retrying or falling back on bad output.

This is the AIA-104 orchestration that ties the constraint (AC1), validation (AC2), and
the invalid-output policy (AC3) together. Its retry is distinct from
:class:`~app.llm.client.LLMClient`'s: the client retries *transport* failures, while this
retries when the provider answered but the answer failed parsing or validation -- it
re-prompts with the error, and after the attempt budget is spent it calls an injected
fallback (e.g. a curated recommendation) or raises the typed error.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

from pydantic import BaseModel

from app.llm.client import LLMClient
from app.llm.types import LLMMessage, LLMRequest, Role
from app.structured.errors import StructuredOutputError
from app.structured.parser import StructuredOutputParser

_RETRY_INSTRUCTION = (
    "Your previous reply was not accepted: {error}. "
    "Reply with ONLY a JSON value matching the required schema, with no extra text."
)


class StructuredCompletion[T: BaseModel]:
    """Run a completion whose result is a validated Pydantic model."""

    def __init__(
        self,
        client: LLMClient,
        parser: StructuredOutputParser[T],
        *,
        max_attempts: int = 2,
        fallback: Callable[[StructuredOutputError], T] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._client = client
        self._parser = parser
        self._max_attempts = max_attempts
        self._fallback = fallback

    def complete(self, request: LLMRequest) -> T:
        """Return the validated result, retrying invalid output then falling back."""
        request = self._ensure_response_format(request)
        messages = list(request.messages)
        last_error: StructuredOutputError | None = None

        for _ in range(self._max_attempts):
            attempt = dataclasses.replace(request, messages=tuple(messages))
            response = self._client.complete(attempt)
            try:
                return self._parser.parse(response.content)
            except StructuredOutputError as exc:
                last_error = exc
                messages.append(LLMMessage(Role.USER, _RETRY_INSTRUCTION.format(error=exc)))

        if last_error is None:  # pragma: no cover - the loop always runs at least once
            raise RuntimeError("structured completion made no attempts")
        if self._fallback is not None:
            return self._fallback(last_error)
        raise last_error

    def _ensure_response_format(self, request: LLMRequest) -> LLMRequest:
        """Attach the parser's schema constraint unless the caller set one already."""
        if request.response_format is not None:
            return request
        return dataclasses.replace(request, response_format=self._parser.response_format())
