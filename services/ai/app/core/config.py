from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via AI_-prefixed environment variables.

    12-factor: every value below is environment-driven so the same image runs in
    dev, CI, and production with no code changes. Secrets (the LLM API key) are
    injected at runtime, never baked into the image.
    """

    model_config = SettingsConfigDict(env_prefix="AI_", env_file=".env", extra="ignore")

    app_name: str = "NutriPlan AI Service"
    environment: str = "development"

    # LLM provider. The client itself (retries/timeouts/calls) arrives in AIA-102;
    # this slice only owns the configuration surface and a readiness signal derived
    # from it. The key is a secret injected per environment (AIA-802).
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2

    @property
    def is_production(self) -> bool:
        """True in production-like environments, where missing deps are fatal."""
        return self.environment.strip().lower() in {"production", "prod"}

    @property
    def llm_configured(self) -> bool:
        """True once an LLM API key is present, so the service can call the provider."""
        return bool(self.llm_api_key.strip())


settings = Settings()
