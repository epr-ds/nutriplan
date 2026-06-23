"""OpenAI Chat Completions adapter.

Maps the vendor-neutral :class:`~app.llm.types.LLMRequest`/``LLMResponse`` onto
OpenAI's ``POST /chat/completions`` wire format and translates HTTP/transport
failures into the :mod:`app.llm.errors` hierarchy the retry client understands. The
API key is sent only as a request header and is never placed in a log line, an
exception message, or this object's ``repr`` (AIA-102 / AIA-802).
"""

from __future__ import annotations

import httpx

from app.llm.errors import (
    LLMAuthError,
    LLMBadRequestError,
    LLMConfigurationError,
    LLMResponseError,
    LLMTimeoutError,
    LLMTransientError,
)
from app.llm.types import LLMRequest, LLMResponse, LLMUsage

_DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider:
    """A hosted-OpenAI :class:`~app.llm.provider.LLMProvider`."""

    name = "openai"

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
        return f"OpenAIProvider(model={self._model!r}, base_url={self._base_url!r})"

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self._api_key.strip():
            raise LLMConfigurationError("OpenAI API key is not configured")

        payload: dict[str, object] = {
            "model": request.model or self._model,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.response_format is not None:
            rf = request.response_format
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": rf.name,
                    "schema": dict(rf.schema),
                    "strict": rf.strict,
                },
            }

        try:
            response = self._client.post(
                "/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("OpenAI request timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMTransientError("OpenAI request failed in transport") from exc

        self._raise_for_status(response)
        return self._parse(response)

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        if status in (401, 403):
            raise LLMAuthError("OpenAI rejected the credentials")
        if status == 429:
            raise LLMTransientError("OpenAI rate limit (429)")
        if status >= 500:
            raise LLMTransientError(f"OpenAI server error ({status})")
        raise LLMBadRequestError(f"OpenAI rejected the request ({status})")

    def _parse(self, response: httpx.Response) -> LLMResponse:
        try:
            body = response.json()
            choice = body["choices"][0]["message"]["content"]
            model = body.get("model", self._model)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("OpenAI response was missing the completion") from exc

        if not isinstance(choice, str):
            raise LLMResponseError("OpenAI completion content was not text")

        return LLMResponse(content=choice, model=model, usage=_parse_usage(body.get("usage")))


def _parse_usage(usage: object) -> LLMUsage | None:
    if not isinstance(usage, dict):
        return None
    try:
        return LLMUsage(
            prompt_tokens=int(usage["prompt_tokens"]),
            completion_tokens=int(usage["completion_tokens"]),
            total_tokens=int(usage["total_tokens"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
