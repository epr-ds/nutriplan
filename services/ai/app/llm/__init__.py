"""Provider-agnostic LLM access for the AI service (AIA-102).

This package is the single seam between the AI service and any hosted LLM. Callers
depend only on the :class:`~app.llm.provider.LLMProvider` port and the value objects
in :mod:`app.llm.types`; concrete adapters (OpenAI, Anthropic, ...) and the
retry/backoff wrapper live behind it so the rest of the service never imports a
vendor SDK or knows which provider is configured.

The public names are re-exported at the bottom of the module once every submodule is
defined.
"""

from app.llm.client import LLMClient
from app.llm.errors import (
    LLMAuthError,
    LLMBadRequestError,
    LLMConfigurationError,
    LLMError,
    LLMResponseError,
    LLMTimeoutError,
    LLMTransientError,
)
from app.llm.factory import build_client, build_provider
from app.llm.fake import FakeLLMProvider
from app.llm.provider import LLMProvider
from app.llm.retry import RetryPolicy, compute_backoff
from app.llm.types import LLMMessage, LLMRequest, LLMResponse, LLMUsage, ResponseFormat, Role

__all__ = [
    "FakeLLMProvider",
    "LLMAuthError",
    "LLMBadRequestError",
    "LLMClient",
    "LLMConfigurationError",
    "LLMError",
    "LLMMessage",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMResponseError",
    "LLMTimeoutError",
    "LLMTransientError",
    "LLMUsage",
    "ResponseFormat",
    "RetryPolicy",
    "Role",
    "build_client",
    "build_provider",
    "compute_backoff",
]
