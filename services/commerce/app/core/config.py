from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via COMMERCE_-prefixed environment variables."""

    model_config = SettingsConfigDict(env_prefix="COMMERCE_", env_file=".env", extra="ignore")

    app_name: str = "NutriPlan Commerce Service"
    environment: str = "development"

    # Persistence
    database_url: str = "postgresql+psycopg://nutriplan:nutriplan@postgres:5432/commerce"

    # Money defaults (COM-101). Orders are priced in MXN unless overridden per order.
    default_currency: str = "MXN"


settings = Settings()
