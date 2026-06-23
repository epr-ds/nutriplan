"""Compose caching and budgets around a base completer (AIA-105).

This is the wiring the ``/ai/*`` endpoints will call from AIA-201. It applies the two
cross-cutting concerns in the order that makes each correct:

1. **Cache first.** A hit returns immediately and costs nothing -- no budget is charged
   for an answer that was already paid for.
2. **Gate on budget.** On a miss, :meth:`TokenBudgetGuard.check` may refuse the call
   before it is made (quota spent, or the global kill-switch latched).
3. **Call, charge, store.** The provider runs once; its real token usage is charged to
   the caller's counters and the answer is cached for next time.

Both collaborators are optional, so the same object also models "cache only", "budget
only", or a plain pass-through, and it satisfies :class:`~app.llm.provider.LLMCompleter`
itself so it can be wrapped in turn.
"""

from __future__ import annotations

from app.budget.factory import build_token_budget_guard
from app.budget.guard import TokenBudgetGuard
from app.budget.policy import BudgetScope
from app.cache.cache import ResponseCache
from app.cache.factory import build_response_cache
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.kv.factory import build_key_value_store
from app.kv.store import KeyValueStore
from app.llm.provider import LLMCompleter
from app.llm.types import LLMRequest, LLMResponse


class CachedCompletionService:
    """Serve completions through an optional cache and budget guard."""

    def __init__(
        self,
        base: LLMCompleter,
        *,
        cache: ResponseCache | None = None,
        guard: TokenBudgetGuard | None = None,
    ) -> None:
        self._base = base
        self._cache = cache
        self._guard = guard

    def complete(
        self,
        request: LLMRequest,
        scope: BudgetScope | None = None,
    ) -> LLMResponse:
        """Return a completion, serving from cache and enforcing budgets as configured."""
        if self._cache is not None:
            cached = self._cache.get(request)
            if cached is not None:
                return cached

        scope = scope or BudgetScope()
        if self._guard is not None:
            self._guard.check(scope)

        response = self._base.complete(request)

        if self._guard is not None and response.usage is not None:
            self._guard.charge(scope, response.usage.total_tokens)
        if self._cache is not None:
            self._cache.put(request, response)
        return response


def build_cached_completion_service(
    base: LLMCompleter,
    settings: Settings | None = None,
    *,
    store: KeyValueStore | None = None,
) -> CachedCompletionService:
    """Wire a service from configuration, sharing one store across cache and budgets."""
    settings = settings or default_settings
    store = store or build_key_value_store(settings)
    cache = build_response_cache(settings, store) if settings.cache_enabled else None
    guard = build_token_budget_guard(settings, store) if settings.budget_enabled else None
    return CachedCompletionService(base, cache=cache, guard=guard)
