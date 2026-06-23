"""Turn a request into a stable cache key.

Two requests that mean the same thing must hash to the same key, so the request is first
reduced to a canonical JSON string: only the fields that change the answer are kept, dicts
are key-sorted (recursively, including the response-format schema), and message order is
preserved because it is meaningful. The key is the SHA-256 of that string under a versioned
namespace, so a format change is a clean cache-miss rather than a silent collision.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from app.llm.types import LLMRequest, ResponseFormat

_VERSION = "v1"


def _plain(value: object) -> object:
    """Recursively coerce mappings/sequences to plain JSON-able containers."""
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _response_format(response_format: ResponseFormat | None) -> object:
    if response_format is None:
        return None
    return {
        "name": response_format.name,
        "strict": response_format.strict,
        "schema": _plain(response_format.schema),
    }


def normalize_request(request: LLMRequest) -> str:
    """Reduce a request to a canonical JSON string for hashing."""
    payload = {
        "model": request.model,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "messages": [[m.role.value, m.content] for m in request.messages],
        "response_format": _response_format(request.response_format),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def cache_key(request: LLMRequest, *, namespace: str) -> str:
    """Return the namespaced, versioned SHA-256 key for ``request``."""
    digest = hashlib.sha256(normalize_request(request).encode("utf-8")).hexdigest()
    return f"{namespace}:{_VERSION}:{digest}"
