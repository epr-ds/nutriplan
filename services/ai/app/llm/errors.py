"""Exception hierarchy for LLM access.

The retry layer keys off the type, not a status code: anything that subclasses
:class:`LLMTransientError` is worth retrying (rate limits, 5xx, timeouts, connection
blips), while everything else (auth, bad request, malformed response, misconfig) is
terminal and re-raised immediately. Adapters map their wire-level failures onto these
so the client stays provider-agnostic.
"""

from __future__ import annotations


class LLMError(Exception):
    """Base class for every LLM access failure."""


class LLMConfigurationError(LLMError):
    """The provider is misconfigured (e.g. missing API key, unknown provider)."""


class LLMTransientError(LLMError):
    """A retryable failure: rate limit, 5xx, or a transport blip."""


class LLMTimeoutError(LLMTransientError):
    """The provider did not respond within the configured timeout (retryable)."""


class LLMAuthError(LLMError):
    """The provider rejected the credentials (401/403); not retryable."""


class LLMBadRequestError(LLMError):
    """The provider rejected the request payload (4xx); not retryable."""


class LLMResponseError(LLMError):
    """The provider replied, but the body was missing or unparseable; not retryable."""
