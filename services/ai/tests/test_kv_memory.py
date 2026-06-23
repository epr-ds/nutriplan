"""Tests for the in-process key-value store: TTL expiry and fixed-window counters."""

from app.kv.memory import InMemoryKeyValueStore


class _Clock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def test_get_returns_none_for_a_missing_key() -> None:
    assert InMemoryKeyValueStore().get("absent") is None


def test_set_then_get_roundtrips() -> None:
    store = InMemoryKeyValueStore()
    store.set("k", "v", ttl_seconds=100)
    assert store.get("k") == "v"


def test_value_expires_once_the_ttl_passes() -> None:
    clock = _Clock()
    store = InMemoryKeyValueStore(clock=clock)
    store.set("k", "v", ttl_seconds=10)

    clock.now += 9
    assert store.get("k") == "v"
    clock.now += 1
    assert store.get("k") is None


def test_zero_ttl_never_expires() -> None:
    clock = _Clock()
    store = InMemoryKeyValueStore(clock=clock)
    store.set("k", "v", ttl_seconds=0)

    clock.now += 10_000
    assert store.get("k") == "v"


def test_increment_creates_a_counter_returning_the_amount() -> None:
    store = InMemoryKeyValueStore()
    assert store.increment("c", 5, ttl_seconds=100) == 5
    assert store.get("c") == "5"


def test_increment_accumulates_within_the_window() -> None:
    store = InMemoryKeyValueStore()
    store.increment("c", 5, ttl_seconds=100)
    assert store.increment("c", 3, ttl_seconds=100) == 8


def test_increment_keeps_the_original_window() -> None:
    clock = _Clock()
    store = InMemoryKeyValueStore(clock=clock)
    store.increment("c", 5, ttl_seconds=10)  # window ends at +10

    clock.now += 5
    store.increment("c", 5, ttl_seconds=10)  # must not push the window to +15
    clock.now += 5
    assert store.get("c") is None


def test_counter_resets_after_the_window() -> None:
    clock = _Clock()
    store = InMemoryKeyValueStore(clock=clock)
    store.increment("c", 5, ttl_seconds=10)

    clock.now += 11
    assert store.increment("c", 2, ttl_seconds=10) == 2
