"""Tests for the cache + budget orchestration (AIA-105)."""

import pytest

from app.budget.errors import GlobalBudgetExceededError
from app.budget.guard import TokenBudgetGuard
from app.budget.policy import BudgetPolicy, BudgetScope
from app.cache.cache import ResponseCache
from app.completions import CachedCompletionService
from app.kv.memory import InMemoryKeyValueStore
from app.llm.fake import FakeLLMProvider
from app.llm.types import LLMMessage, LLMRequest, LLMResponse, LLMUsage, Role

_REQUEST = LLMRequest.of([LLMMessage(Role.USER, "plan")])


def _response(content: str = "ok", *, total: int = 5) -> LLMResponse:
    return LLMResponse(content=content, model="m", usage=LLMUsage(0, total, total))


def _cache(store: InMemoryKeyValueStore) -> ResponseCache:
    return ResponseCache(store, ttl_seconds=100, namespace="ai:cache")


def test_cache_hit_is_free_and_skips_the_provider() -> None:
    store = InMemoryKeyValueStore()
    guard = TokenBudgetGuard(store, BudgetPolicy(global_tokens=100), namespace="ai:budget")
    provider = FakeLLMProvider([_response("first", total=5)])
    service = CachedCompletionService(provider, cache=_cache(store), guard=guard)

    first = service.complete(_REQUEST, BudgetScope(user_id="u1"))
    second = service.complete(_REQUEST, BudgetScope(user_id="u1"))

    assert second == first
    assert provider.call_count == 1  # the second call was served from cache
    assert store.get("ai:budget:global") == "5"  # and was not charged again


def test_miss_charges_the_budget_and_caches() -> None:
    store = InMemoryKeyValueStore()
    guard = TokenBudgetGuard(store, BudgetPolicy(per_user_tokens=1_000), namespace="ai:budget")
    cache = _cache(store)
    provider = FakeLLMProvider([_response(total=7)])
    service = CachedCompletionService(provider, cache=cache, guard=guard)

    service.complete(_REQUEST, BudgetScope(user_id="u1"))

    assert store.get("ai:budget:user:u1") == "7"
    assert cache.get(_REQUEST) is not None


def test_budget_block_prevents_the_provider_call() -> None:
    store = InMemoryKeyValueStore()
    guard = TokenBudgetGuard(store, BudgetPolicy(global_tokens=10), namespace="ai:budget")
    provider = FakeLLMProvider([_response(total=10), _response(total=10)])
    service = CachedCompletionService(provider, guard=guard)

    service.complete(LLMRequest.of([LLMMessage(Role.USER, "a")]), BudgetScope(user_id="u1"))
    with pytest.raises(GlobalBudgetExceededError):
        service.complete(LLMRequest.of([LLMMessage(Role.USER, "b")]), BudgetScope(user_id="u1"))

    assert provider.call_count == 1  # the refused call never reached the provider


def test_pass_through_without_cache_or_guard() -> None:
    provider = FakeLLMProvider([_response("x", total=3)])
    service = CachedCompletionService(provider)
    assert service.complete(_REQUEST).content == "x"


def test_missing_scope_falls_back_to_the_default() -> None:
    store = InMemoryKeyValueStore()
    guard = TokenBudgetGuard(store, BudgetPolicy(global_tokens=100), namespace="ai:budget")
    provider = FakeLLMProvider([_response(total=4)])
    service = CachedCompletionService(provider, guard=guard)

    service.complete(_REQUEST)

    assert store.get("ai:budget:global") == "4"
