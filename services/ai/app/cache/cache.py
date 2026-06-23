"""Read-through storage for completions, keyed on the normalized request (AIA-105, AC1).

A repeated request is cheap because its answer is served from the store instead of the
provider, for a configurable TTL. The cache is deliberately oblivious to budgets: callers
check it *before* the budget gate so a hit costs no tokens. A value that fails to decode
(corruption or a superseded format) is treated as a miss rather than an error, so a bad
entry degrades to a fresh call instead of a failure.
"""

from __future__ import annotations

import json

from app.cache.keys import cache_key
from app.kv.store import KeyValueStore
from app.llm.types import LLMRequest, LLMResponse, LLMUsage


def _encode(response: LLMResponse) -> str:
    usage = response.usage
    return json.dumps(
        {
            "content": response.content,
            "model": response.model,
            "usage": None
            if usage is None
            else {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            },
        }
    )


def _decode(raw: str) -> LLMResponse:
    data = json.loads(raw)
    usage = data["usage"]
    return LLMResponse(
        content=data["content"],
        model=data["model"],
        usage=None
        if usage is None
        else LLMUsage(
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
        ),
    )


class ResponseCache:
    """Store and retrieve :class:`~app.llm.types.LLMResponse` values by request."""

    def __init__(
        self,
        store: KeyValueStore,
        *,
        ttl_seconds: int,
        namespace: str = "ai:cache",
    ) -> None:
        self._store = store
        self._ttl_seconds = ttl_seconds
        self._namespace = namespace

    def get(self, request: LLMRequest) -> LLMResponse | None:
        """Return the cached response for ``request``, or ``None`` on a miss."""
        raw = self._store.get(cache_key(request, namespace=self._namespace))
        if raw is None:
            return None
        try:
            return _decode(raw)
        except (ValueError, KeyError):  # corrupt or superseded entry -> treat as a miss
            return None

    def put(self, request: LLMRequest, response: LLMResponse) -> None:
        """Store ``response`` for ``request`` under the configured TTL."""
        self._store.set(
            cache_key(request, namespace=self._namespace),
            _encode(response),
            ttl_seconds=self._ttl_seconds,
        )
