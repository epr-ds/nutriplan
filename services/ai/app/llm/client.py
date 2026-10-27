"""The resilience wrapper: retries transient provider failures with backoff.

:class:`LLMClient` is provider-agnostic — it wraps any :class:`~app.llm.provider.\
LLMProvider` and adds cross-cutting retry/backoff. Per-call timeouts already live in
the adapters (surfaced as :class:`~app.llm.errors.LLMTimeoutError`, which is
transient). Only transient errors are retried; terminal ones (auth, bad request,
malformed response) propagate on the first attempt. ``sleep`` and ``rand`` are
injected so the policy can be exercised with no real delay or randomness.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable

from app.core.telemetry import (
    ai_llm_cost_usd_total,
    ai_llm_usage_completion_tokens_total,
    ai_llm_usage_prompt_tokens_total,
    ai_llm_usage_total,
    current_route,
    llm_cost_usd,
)
from app.llm.errors import LLMTransientError
from app.llm.provider import LLMProvider
from app.llm.retry import RetryPolicy, compute_backoff
from app.llm.types import LLMRequest, LLMResponse


class LLMClient:
    """Wrap a provider with bounded retries and exponential backoff."""

    def __init__(
        self,
        provider: LLMProvider,
        policy: RetryPolicy | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        rand: Callable[[], float] = random.random,
    ) -> None:
        self._provider = provider
        self._policy = policy or RetryPolicy()
        self._sleep = sleep
        self._rand = rand

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def max_retries(self) -> int:
        return self._policy.max_retries

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Run the completion, retrying transient failures per the policy."""
        last_error: LLMTransientError | None = None
        for attempt in range(self._policy.max_retries + 1):
            try:
                response = self._provider.complete(request)
                self._record_usage(response)
                return response
            except LLMTransientError as exc:
                last_error = exc
                if attempt >= self._policy.max_retries:
                    break
                self._sleep(compute_backoff(attempt, self._policy, self._rand))
        assert last_error is not None  # the loop only breaks after catching one
        raise last_error

    def _record_usage(self, response: LLMResponse) -> None:
        """Count token usage for the cost & usage dashboard (AIA-805)."""
        usage = response.usage
        if usage is None:
            return
        ai_llm_usage_total.labels(response.model or "").inc(usage.total_tokens)
        ai_llm_usage_prompt_tokens_total.labels(response.model or "").inc(usage.prompt_tokens)
        ai_llm_usage_completion_tokens_total.labels(response.model or "").inc(
            usage.completion_tokens
        )
        ai_llm_cost_usd_total.labels(response.model or "", current_route.get()).inc(
            llm_cost_usd(response.model or "", usage.prompt_tokens, usage.completion_tokens)
        )
