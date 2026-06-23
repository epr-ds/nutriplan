"""Immutable value objects exchanged with any LLM provider.

These are deliberately vendor-neutral: each adapter maps them to/from its own wire
format, so the rest of the service speaks one shape regardless of which provider is
configured. Prompt assembly (AIA-103) and structured-output parsing (AIA-104) build
on top of these.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    """Who authored a message in the conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """A single chat message."""

    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class ResponseFormat:
    """Asks the provider to constrain its reply to a named JSON schema (AIA-104).

    Each adapter maps this onto the vendor's native mechanism (OpenAI structured-output
    ``response_format``, Anthropic forced tool use). It is only a *request* to the
    provider, so the output is still parsed and validated on our side after the call.
    """

    name: str
    schema: Mapping[str, Any]
    strict: bool = True


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """A completion request, independent of any provider.

    ``model`` is optional: when ``None`` the adapter falls back to its configured
    default, so callers only override it when they need a specific model.
    """

    messages: tuple[LLMMessage, ...]
    model: str | None = None
    temperature: float = 0.2
    max_tokens: int | None = None
    response_format: ResponseFormat | None = None

    @classmethod
    def of(
        cls,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        response_format: ResponseFormat | None = None,
    ) -> LLMRequest:
        """Build a request from any message sequence (stored as an immutable tuple)."""
        return cls(
            messages=tuple(messages),
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """Token accounting for a single completion (drives cost/quota work in AIA-105)."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """A completion result, normalized across providers."""

    content: str
    model: str
    usage: LLMUsage | None = None
