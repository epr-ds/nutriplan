"""Tests for request normalization and cache-key derivation (AIA-105, AC1)."""

from app.cache.keys import cache_key, normalize_request
from app.llm.types import LLMMessage, LLMRequest, ResponseFormat, Role


def _req(**kwargs) -> LLMRequest:
    return LLMRequest.of([LLMMessage(Role.USER, "hi")], **kwargs)


def test_identical_requests_share_a_key() -> None:
    assert cache_key(_req(), namespace="ns") == cache_key(_req(), namespace="ns")


def test_different_message_changes_the_key() -> None:
    a = cache_key(LLMRequest.of([LLMMessage(Role.USER, "a")]), namespace="ns")
    b = cache_key(LLMRequest.of([LLMMessage(Role.USER, "b")]), namespace="ns")
    assert a != b


def test_message_order_is_significant() -> None:
    ordered = [LLMMessage(Role.SYSTEM, "s"), LLMMessage(Role.USER, "u")]
    a = cache_key(LLMRequest.of(ordered), namespace="ns")
    b = cache_key(LLMRequest.of(list(reversed(ordered))), namespace="ns")
    assert a != b


def test_sampling_settings_change_the_key() -> None:
    assert cache_key(_req(temperature=0.1), namespace="ns") != cache_key(
        _req(temperature=0.9), namespace="ns"
    )
    assert cache_key(_req(model="x"), namespace="ns") != cache_key(_req(model="y"), namespace="ns")


def test_namespace_and_version_prefix_the_key() -> None:
    assert cache_key(_req(), namespace="ai:cache").startswith("ai:cache:v1:")


def test_response_format_schema_key_order_is_canonical() -> None:
    a = _req(response_format=ResponseFormat(name="P", schema={"a": 1, "b": {"c": 2, "d": 3}}))
    b = _req(response_format=ResponseFormat(name="P", schema={"b": {"d": 3, "c": 2}, "a": 1}))
    assert cache_key(a, namespace="ns") == cache_key(b, namespace="ns")


def test_response_format_presence_changes_the_key() -> None:
    plain = cache_key(_req(), namespace="ns")
    constrained = cache_key(
        _req(response_format=ResponseFormat(name="P", schema={"a": 1})), namespace="ns"
    )
    assert plain != constrained


def test_normalize_request_is_deterministic_json() -> None:
    assert normalize_request(_req()) == normalize_request(_req())
