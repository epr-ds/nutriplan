from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via AI_-prefixed environment variables."""

    model_config = SettingsConfigDict(env_prefix="AI_", env_file=".env", extra="ignore")

    app_name: str = "NutriPlan AI Service"
    environment: str = "development"
    llm_provider: str = "openai"
    llm_api_key: str = ""


settings = Settings()
