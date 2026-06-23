"""Anthropic Messages adapter.

Anthropic's ``POST /v1/messages`` wire format differs from OpenAI's in three ways the
shared port has to absorb: the credential rides an ``x-api-key`` header (plus a
required ``anthropic-version``), the system prompt is a top-level ``system`` field
rather than a message, and the completion comes back as a list of typed content
blocks. Implementing it concretely proves the single :class:`~app.llm.provider.\
LLMProvider` abstraction is genuinely provider-agnostic. As with OpenAI, the key
never appears in a log, exception, or ``repr``.
"""

from __future__ import annotations

import json

import httpx

from app.llm.errors import (
    LLMAuthError,
    LLMBadRequestError,
    LLMConfigurationError,
    LLMResponseError,
    LLMTimeoutError,
    LLMTransientError,
)
from app.llm.types import LLMRequest, LLMResponse, LLMUsage, ResponseFormat, Role

_DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 1024


class AnthropicProvider:
    """A hosted-Anthropic :class:`~app.llm.provider.LLMProvider`."""

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(base_url=self._base_url, timeout=timeout)

    def __repr__(self) -> str:  # keep the secret out of logs and tracebacks
        return f"AnthropicProvider(model={self._model!r}, base_url={self._base_url!r})"

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self._api_key.strip():
            raise LLMConfigurationError("Anthropic API key is not configured")

        system = " ".join(m.content for m in request.messages if m.role is Role.SYSTEM)
        turns = [
            {"role": m.role.value, "content": m.content}
            for m in request.messages
            if m.role is not Role.SYSTEM
        ]
        payload: dict[str, object] = {
            "model": request.model or self._model,
            "messages": turns,
            "max_tokens": request.max_tokens or _DEFAULT_MAX_TOKENS,
            "temperature": request.temperature,
        }
        if system:
            payload["system"] = system
        if request.response_format is not None:
            rf = request.response_format
            payload["tools"] = [{"name": rf.name, "input_schema": dict(rf.schema)}]
            payload["tool_choice"] = {"type": "tool", "name": rf.name}

        try:
            response = self._client.post(
                "/messages",
                json=payload,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": _ANTHROPIC_VERSION,
                },
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Anthropic request timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMTransientError("Anthropic request failed in transport") from exc

        self._raise_for_status(response)
        return self._parse(response, request.response_format)

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        if status in (401, 403):
            raise LLMAuthError("Anthropic rejected the credentials")
        if status == 429:
            raise LLMTransientError("Anthropic rate limit (429)")
        if status >= 500:
            raise LLMTransientError(f"Anthropic server error ({status})")
        raise LLMBadRequestError(f"Anthropic rejected the request ({status})")

    def _parse(
        self, response: httpx.Response, response_format: ResponseFormat | None
    ) -> LLMResponse:
        try:
            body = response.json()
            blocks = body["content"]
            model = body.get("model", self._model)
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMResponseError("Anthropic response was missing the completion") from exc

        if not isinstance(blocks, list):
            raise LLMResponseError("Anthropic response content was not a list")

        usage = _parse_usage(body.get("usage"))

        # When a tool was forced (structured output, AIA-104) the answer comes back as a
        # tool_use block whose ``input`` is the JSON object, not as free text. Normalize
        # it to a JSON string so callers parse content uniformly across providers.
        if response_format is not None:
            for block in blocks:
                if block.get("type") == "tool_use" and block.get("name") == response_format.name:
                    return LLMResponse(
                        content=json.dumps(block.get("input", {})), model=model, usage=usage
                    )
            raise LLMResponseError("Anthropic response did not include the requested tool output")

        try:
            text = "".join(block["text"] for block in blocks if block.get("type") == "text")
        except (KeyError, TypeError) as exc:
            raise LLMResponseError("Anthropic response had a malformed text block") from exc

        if not text:
            raise LLMResponseError("Anthropic response contained no text content")

        return LLMResponse(content=text, model=model, usage=usage)


def _parse_usage(usage: object) -> LLMUsage | None:
    if not isinstance(usage, dict):
        return None
    try:
        prompt = int(usage["input_tokens"])
        completion = int(usage["output_tokens"])
    except (KeyError, TypeError, ValueError):
        return None
    return LLMUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
    )
