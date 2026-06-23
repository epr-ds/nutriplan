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

    # Response cache + token budgets (AIA-105). Redis backs both so the cache and the
    # quota counters are shared across replicas; leave AI_REDIS_URL blank and an
    # in-process store is used (correct for dev/CI and a single replica, not shared).
    # A token limit of 0 disables that dimension, keeping quotas opt-in; the global
    # limit doubles as a kill-switch that latches for the window once it is exceeded.
    redis_url: str = ""
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600
    cache_namespace: str = "ai:cache"
    budget_enabled: bool = True
    budget_window_seconds: int = 86_400
    budget_per_user_tokens: int = 0
    budget_per_route_tokens: int = 0
    budget_global_tokens: int = 0
    budget_namespace: str = "ai:budget"

    @property
    def is_production(self) -> bool:
        """True in production-like environments, where missing deps are fatal."""
        return self.environment.strip().lower() in {"production", "prod"}

    @property
    def llm_configured(self) -> bool:
        """True once an LLM API key is present, so the service can call the provider."""
        return bool(self.llm_api_key.strip())


settings = Settings()
