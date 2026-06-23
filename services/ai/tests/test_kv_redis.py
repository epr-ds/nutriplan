"""Tests for the Redis adapter via a duck-typed fake client (no server required).

These assert the adapter issues the *right* Redis operations -- ``SET ... EX`` for TTLs and
``EXPIRE`` only on a counter's first write -- which is what the in-memory store cannot prove.
"""

from app.kv.redis_store import RedisKeyValueStore


class FakeRedis:
    """A minimal in-dict stand-in that records every call made to it."""

    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.calls: list[tuple] = []

    def get(self, key: str):
        self.calls.append(("get", key))
        return self.values.get(key)

    def set(self, key: str, value: str, ex: int | None = None):
        self.calls.append(("set", key, value, ex))
        self.values[key] = value

    def incrby(self, key: str, amount: int) -> int:
        self.calls.append(("incrby", key, amount))
        self.values[key] = int(self.values.get(key, 0)) + amount
        return self.values[key]

    def expire(self, key: str, seconds: int):
        self.calls.append(("expire", key, seconds))


def test_set_passes_ttl_as_ex() -> None:
    client = FakeRedis()
    RedisKeyValueStore(client).set("k", "v", ttl_seconds=30)
    assert ("set", "k", "v", 30) in client.calls


def test_set_without_ttl_omits_ex() -> None:
    client = FakeRedis()
    RedisKeyValueStore(client).set("k", "v", ttl_seconds=0)
    assert ("set", "k", "v", None) in client.calls


def test_get_decodes_bytes() -> None:
    client = FakeRedis()
    client.values["k"] = b"v"
    assert RedisKeyValueStore(client).get("k") == "v"


def test_get_returns_str_unchanged() -> None:
    client = FakeRedis()
    client.values["k"] = "v"
    assert RedisKeyValueStore(client).get("k") == "v"


def test_get_missing_is_none() -> None:
    assert RedisKeyValueStore(FakeRedis()).get("absent") is None


def test_increment_sets_expiry_only_on_the_first_write() -> None:
    client = FakeRedis()
    store = RedisKeyValueStore(client)

    assert store.increment("c", 5, ttl_seconds=60) == 5
    assert ("expire", "c", 60) in client.calls

    client.calls.clear()
    assert store.increment("c", 5, ttl_seconds=60) == 10
    assert all(call[0] != "expire" for call in client.calls)


def test_increment_skips_expiry_when_ttl_is_zero() -> None:
    client = FakeRedis()
    RedisKeyValueStore(client).increment("c", 5, ttl_seconds=0)
    assert all(call[0] != "expire" for call in client.calls)
