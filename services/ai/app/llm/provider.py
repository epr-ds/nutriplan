"""The provider port — the one abstraction every LLM vendor sits behind.

A provider performs exactly one network round-trip per :meth:`complete` call and maps
vendor failures onto :mod:`app.llm.errors`. Cross-cutting resilience (timeouts already
applied per-call, plus retries/backoff) lives in :class:`~app.llm.client.LLMClient`,
which wraps any provider — so adapters stay thin and single-purpose.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.llm.types import LLMRequest, LLMResponse


@runtime_checkable
class LLMProvider(Protocol):
    """A provider-agnostic completion backend (OpenAI, Anthropic, Vertex, ...)."""

    name: str

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Run one completion, raising an :class:`~app.llm.errors.LLMError` on failure."""
        ...
