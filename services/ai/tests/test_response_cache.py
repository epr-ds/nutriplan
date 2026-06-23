"""Tests for read-through response caching (AIA-105, AC1)."""

from app.cache.cache import ResponseCache
from app.cache.keys import cache_key
from app.kv.memory import InMemoryKeyValueStore
from app.llm.types import LLMMessage, LLMRequest, LLMResponse, LLMUsage, Role

_REQUEST = LLMRequest.of([LLMMessage(Role.USER, "hi")])


class _Clock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def _cache(store: InMemoryKeyValueStore | None = None, *, ttl: int = 100) -> ResponseCache:
    return ResponseCache(store or InMemoryKeyValueStore(), ttl_seconds=ttl, namespace="ai:cache")


def test_miss_returns_none() -> None:
    assert _cache().get(_REQUEST) is None


def test_put_then_get_roundtrips_with_usage() -> None:
    cache = _cache()
    response = LLMResponse(content="hello", model="m", usage=LLMUsage(1, 2, 3))
    cache.put(_REQUEST, response)
    assert cache.get(_REQUEST) == response


def test_roundtrips_without_usage() -> None:
    cache = _cache()
    response = LLMResponse(content="hi", model="m")
    cache.put(_REQUEST, response)
    assert cache.get(_REQUEST) == response


def test_entry_expires_after_ttl() -> None:
    clock = _Clock()
    cache = _cache(InMemoryKeyValueStore(clock=clock), ttl=10)
    cache.put(_REQUEST, LLMResponse(content="x", model="m"))

    clock.now += 11
    assert cache.get(_REQUEST) is None


def test_corrupt_entry_is_treated_as_a_miss() -> None:
    store = InMemoryKeyValueStore()
    cache = ResponseCache(store, ttl_seconds=10, namespace="ai:cache")
    store.set(cache_key(_REQUEST, namespace="ai:cache"), "not json", ttl_seconds=10)
    assert cache.get(_REQUEST) is None


def test_different_requests_do_not_collide() -> None:
    cache = _cache()
    cache.put(_REQUEST, LLMResponse(content="one", model="m"))
    other = LLMRequest.of([LLMMessage(Role.USER, "different")])
    assert cache.get(other) is None
