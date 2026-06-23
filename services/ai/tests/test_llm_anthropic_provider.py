"""Offline tests for the Anthropic adapter using httpx.MockTransport (AIA-102).

These focus on the ways Anthropic's wire format differs from OpenAI's — the
``x-api-key``/``anthropic-version`` headers, the hoisted ``system`` field, and the
typed content-block response — to prove the shared port absorbs both shapes.
"""

import json

import httpx
import pytest

from app.llm.anthropic_provider import AnthropicProvider
from app.llm.errors import LLMAuthError, LLMResponseError, LLMTransientError
from app.llm.types import LLMMessage, LLMRequest, Role

_API_KEY = "sk-ant-secret-do-not-log"


def _provider(handler, *, api_key: str = _API_KEY) -> AnthropicProvider:
    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.anthropic.test/v1"
    )
    return AnthropicProvider(api_key=api_key, model="claude-3-5-sonnet", client=client)


def _ok_body(text: str = "Hello!") -> dict:
    return {
        "model": "claude-3-5-sonnet",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 9, "output_tokens": 5},
    }


def test_complete_hoists_system_and_sets_headers() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["x_api_key"] = request.headers.get("x-api-key")
        captured["version"] = request.headers.get("anthropic-version")
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body("Hi"))

    request = LLMRequest.of(
        [LLMMessage(Role.SYSTEM, "be brief"), LLMMessage(Role.USER, "hi")],
        max_tokens=512,
    )
    result = _provider(handler).complete(request)

    assert captured["url"].endswith("/messages")
    assert captured["x_api_key"] == _API_KEY
    assert captured["version"] == "2023-06-01"
    assert captured["json"]["system"] == "be brief"
    assert captured["json"]["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["json"]["max_tokens"] == 512

    assert result.content == "Hi"
    assert result.usage is not None
    assert result.usage.total_tokens == 14  # 9 input + 5 output


def test_max_tokens_defaults_when_unset() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body())

    _provider(handler).complete(LLMRequest.of([LLMMessage(Role.USER, "hi")]))

    assert captured["json"]["max_tokens"] == 1024  # Anthropic requires max_tokens
    assert "system" not in captured["json"]  # no system message -> field omitted


def test_concatenates_text_blocks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = {
            "model": "claude-3-5-sonnet",
            "content": [
                {"type": "text", "text": "part one "},
                {"type": "tool_use", "id": "x"},
                {"type": "text", "text": "part two"},
            ],
            "usage": {"input_tokens": 3, "output_tokens": 4},
        }
        return httpx.Response(200, json=body)

    result = _provider(handler).complete(LLMRequest.of([LLMMessage(Role.USER, "hi")]))

    assert result.content == "part one part two"


def test_429_maps_to_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    with pytest.raises(LLMTransientError):
        _provider(handler).complete(LLMRequest.of([LLMMessage(Role.USER, "hi")]))


def test_empty_content_maps_to_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "x", "content": []})

    with pytest.raises(LLMResponseError):
        _provider(handler).complete(LLMRequest.of([LLMMessage(Role.USER, "hi")]))


def test_api_key_never_appears_in_repr_or_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    provider = _provider(handler)
    assert _API_KEY not in repr(provider)

    try:
        provider.complete(LLMRequest.of([LLMMessage(Role.USER, "hi")]))
    except LLMAuthError as exc:
        assert _API_KEY not in str(exc)
    else:  # pragma: no cover - the call must raise
        raise AssertionError("expected LLMAuthError")
