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
from app.llm.types import LLMMessage, LLMRequest, ResponseFormat, Role

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


def test_response_format_forces_a_tool_and_parses_tool_use() -> None:
    captured: dict = {}
    schema = {
        "type": "object",
        "properties": {"x": {"type": "integer"}},
        "required": ["x"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        body = {
            "model": "claude-3-5-sonnet",
            "content": [{"type": "tool_use", "name": "Result", "input": {"x": 7}}],
            "usage": {"input_tokens": 2, "output_tokens": 3},
        }
        return httpx.Response(200, json=body)

    request = LLMRequest.of(
        [LLMMessage(Role.USER, "hi")],
        response_format=ResponseFormat(name="Result", schema=schema),
    )
    result = _provider(handler).complete(request)

    assert captured["json"]["tools"] == [{"name": "Result", "input_schema": schema}]
    assert captured["json"]["tool_choice"] == {"type": "tool", "name": "Result"}
    # The tool_use input is normalized back into JSON text for uniform parsing.
    assert json.loads(result.content) == {"x": 7}


def test_missing_tool_use_when_forced_maps_to_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"model": "x", "content": [{"type": "text", "text": "oops"}]},
        )

    request = LLMRequest.of(
        [LLMMessage(Role.USER, "hi")],
        response_format=ResponseFormat(name="Result", schema={"type": "object"}),
    )
    with pytest.raises(LLMResponseError):
        _provider(handler).complete(request)


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
