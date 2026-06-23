"""Tests for provider/client selection from configuration (AIA-102)."""

import pytest

from app.core.config import Settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.errors import LLMConfigurationError
from app.llm.factory import build_client, build_provider
from app.llm.fake import FakeLLMProvider
from app.llm.openai_provider import OpenAIProvider


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"llm_api_key": "sk-test", "llm_max_retries": 4}
    base.update(overrides)
    return Settings(**base)


def test_builds_openai_by_default() -> None:
    provider = build_provider(_settings(llm_provider="openai"))
    assert isinstance(provider, OpenAIProvider)
    assert provider.name == "openai"


def test_builds_anthropic() -> None:
    provider = build_provider(_settings(llm_provider="anthropic"))
    assert isinstance(provider, AnthropicProvider)


def test_builds_fake_without_requiring_a_key() -> None:
    provider = build_provider(_settings(llm_provider="fake", llm_api_key=""))
    assert isinstance(provider, FakeLLMProvider)


def test_provider_name_is_case_insensitive() -> None:
    assert build_provider(_settings(llm_provider="OpenAI")).name == "openai"


def test_vertex_is_recognized_but_not_yet_implemented() -> None:
    with pytest.raises(LLMConfigurationError, match="Vertex"):
        build_provider(_settings(llm_provider="vertex"))


def test_unknown_provider_raises() -> None:
    with pytest.raises(LLMConfigurationError, match="unsupported"):
        build_provider(_settings(llm_provider="llamafarm"))


def test_build_client_wires_retry_budget_from_settings() -> None:
    client = build_client(_settings(llm_provider="fake", llm_max_retries=4))
    assert client.provider_name == "fake"
    assert client.max_retries == 4
