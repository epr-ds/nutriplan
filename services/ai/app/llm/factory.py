"""Build a provider/client from configuration.

This is the only place that maps the ``AI_LLM_PROVIDER`` setting to a concrete
adapter, so the rest of the service asks for a :class:`~app.llm.client.LLMClient`
without hard-coding a vendor. ``vertex`` is a recognized provider name but has no
adapter yet — Vertex AI authenticates with GCP service-account credentials rather
than a simple API key, so it lands in its own slice; until then the factory fails
loudly instead of silently degrading.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.client import LLMClient
from app.llm.errors import LLMConfigurationError
from app.llm.fake import FakeLLMProvider
from app.llm.openai_provider import OpenAIProvider
from app.llm.provider import LLMProvider
from app.llm.retry import RetryPolicy

_HOSTED = {"openai": OpenAIProvider, "anthropic": AnthropicProvider}


def build_provider(settings: Settings | None = None) -> LLMProvider:
    """Construct the configured provider (defaults to the process settings)."""
    settings = settings or default_settings
    name = settings.llm_provider.strip().lower()

    if name == "fake":
        return FakeLLMProvider(model=settings.llm_model)

    if name == "vertex":
        raise LLMConfigurationError(
            "Vertex AI requires GCP credentials; its adapter is not implemented yet"
        )

    provider_cls = _HOSTED.get(name)
    if provider_cls is None:
        raise LLMConfigurationError(f"unsupported LLM provider: {name!r}")

    return provider_cls(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
    )


def build_client(settings: Settings | None = None) -> LLMClient:
    """Construct the retry/backoff client around the configured provider."""
    settings = settings or default_settings
    return LLMClient(
        build_provider(settings),
        RetryPolicy(max_retries=settings.llm_max_retries),
    )
