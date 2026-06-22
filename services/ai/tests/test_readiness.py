"""Pure unit tests for the AI service readiness evaluation (AIA-101).

Readiness is distinct from liveness: a process can be *alive* (answering `/health`)
yet *not ready* to serve AI traffic because a required dependency — here, the LLM
provider credentials — is missing. The evaluation is environment-aware: outside
production a missing key degrades to a non-fatal ``warn`` (so dev/CI come up and the
non-LLM surface stays testable), while in production it is a hard ``fail``.
"""

from app.core.config import Settings
from app.core.readiness import evaluate_readiness


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"llm_api_key": "", "environment": "development"}
    base.update(overrides)
    return Settings(**base)


def test_configured_provider_is_ok_and_ready() -> None:
    result = evaluate_readiness(_settings(llm_api_key="sk-test", llm_provider="openai"))

    assert result.ready is True
    check = result.check("llm_provider")
    assert check.status == "ok"
    assert "openai" in check.detail


def test_missing_key_in_development_warns_but_stays_ready() -> None:
    result = evaluate_readiness(_settings(llm_api_key="", environment="development"))

    assert result.ready is True
    assert result.check("llm_provider").status == "warn"


def test_missing_key_in_production_fails_and_is_not_ready() -> None:
    result = evaluate_readiness(_settings(llm_api_key="", environment="production"))

    assert result.ready is False
    assert result.check("llm_provider").status == "fail"


def test_configured_key_in_production_is_ready() -> None:
    result = evaluate_readiness(_settings(llm_api_key="sk-live", environment="production"))

    assert result.ready is True
    assert result.check("llm_provider").status == "ok"


def test_production_flag_tracks_environment() -> None:
    assert _settings(environment="production").is_production is True
    assert _settings(environment="prod").is_production is True
    assert _settings(environment="development").is_production is False


def test_llm_configured_reflects_api_key_presence() -> None:
    assert _settings(llm_api_key="sk-test").llm_configured is True
    assert _settings(llm_api_key="").llm_configured is False
