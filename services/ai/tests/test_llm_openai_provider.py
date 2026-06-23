"""Offline tests for the OpenAI adapter using httpx.MockTransport (AIA-102).

MockTransport lets us exercise the real request-building, response-parsing, and
HTTP-status-to-error mapping paths without a network or an API key — the handler
stands in for OpenAI and can also raise transport errors.
"""

import json

import httpx
import pytest

from app.llm.errors import (
    LLMAuthError,
    LLMBadRequestError,
    LLMConfigurationError,
    LLMResponseError,
    LLMTimeoutError,
    LLMTransientError,
)
from app.llm.openai_provider import OpenAIProvider
from app.llm.types import LLMMessage, LLMRequest, ResponseFormat, Role

_API_KEY = "sk-secret-do-not-log"


def _provider(handler, *, api_key: str = _API_KEY, model: str = "gpt-4o-mini") -> OpenAIProvider:
    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.openai.test/v1"
    )
    return OpenAIProvider(api_key=api_key, model=model, client=client)


def _ok_body(content: str = "Hello!", model: str = "gpt-4o-mini") -> dict:
    return {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


def test_complete_builds_request_and_parses_response() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body("Hi there"))

    request = LLMRequest.of(
        [LLMMessage(Role.SYSTEM, "be brief"), LLMMessage(Role.USER, "hi")],
        temperature=0.4,
    )
    result = _provider(handler).complete(request)

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/chat/completions")
    assert captured["auth"] == f"Bearer {_API_KEY}"
    assert captured["json"]["model"] == "gpt-4o-mini"
    assert captured["json"]["temperature"] == 0.4
    assert captured["json"]["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
    ]
    assert "max_tokens" not in captured["json"]  # omitted when unset

    assert result.content == "Hi there"
    assert result.model == "gpt-4o-mini"
    assert result.usage is not None
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens == 7
    assert result.usage.total_tokens == 18


def test_response_format_is_emitted_as_json_schema() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body('{"x": 1}'))

    schema = {
        "type": "object",
        "properties": {"x": {"type": "integer"}},
        "required": ["x"],
        "additionalProperties": False,
    }
    request = LLMRequest.of(
        [LLMMessage(Role.USER, "hi")],
        response_format=ResponseFormat(name="Result", schema=schema),
    )
    _provider(handler).complete(request)

    fmt = captured["json"]["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "Result"
    assert fmt["json_schema"]["schema"] == schema
    assert fmt["json_schema"]["strict"] is True


def test_request_model_and_max_tokens_override_defaults() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body())

    request = LLMRequest.of([LLMMessage(Role.USER, "hi")], model="gpt-4o", max_tokens=256)
    _provider(handler).complete(request)

    assert captured["json"]["model"] == "gpt-4o"
    assert captured["json"]["max_tokens"] == 256


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, LLMTransientError),
        (500, LLMTransientError),
        (503, LLMTransientError),
        (401, LLMAuthError),
        (403, LLMAuthError),
        (400, LLMBadRequestError),
        (422, LLMBadRequestError),
    ],
)
def test_http_status_maps_to_error(status: int, expected: type[Exception]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "nope"}})

    with pytest.raises(expected):
        _provider(handler).complete(LLMRequest.of([LLMMessage(Role.USER, "hi")]))


def test_timeout_maps_to_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(LLMTimeoutError):
        _provider(handler).complete(LLMRequest.of([LLMMessage(Role.USER, "hi")]))


def test_transport_error_maps_to_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMTransientError):
        _provider(handler).complete(LLMRequest.of([LLMMessage(Role.USER, "hi")]))


def test_malformed_body_maps_to_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    with pytest.raises(LLMResponseError):
        _provider(handler).complete(LLMRequest.of([LLMMessage(Role.USER, "hi")]))


def test_missing_api_key_raises_configuration_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - never called
        return httpx.Response(200, json=_ok_body())

    with pytest.raises(LLMConfigurationError):
        _provider(handler, api_key="").complete(LLMRequest.of([LLMMessage(Role.USER, "hi")]))


def test_api_key_never_appears_in_repr_or_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    provider = _provider(handler)
    assert _API_KEY not in repr(provider)

    try:
        provider.complete(LLMRequest.of([LLMMessage(Role.USER, "hi")]))
    except LLMAuthError as exc:
        assert _API_KEY not in str(exc)
    else:  # pragma: no cover - the call must raise
        raise AssertionError("expected LLMAuthError")
