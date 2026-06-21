from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via DIETARY_-prefixed environment variables."""

    model_config = SettingsConfigDict(env_prefix="DIETARY_", env_file=".env", extra="ignore")

    app_name: str = "NutriPlan Dietary Planning Service"
    environment: str = "development"

    # Persistence (MongoDB). The default targets the compose `mongo` service, whose root
    # credentials live in the admin database (hence authSource=admin).
    mongo_url: str = "mongodb://nutriplan:nutriplan@mongo:27017/?authSource=admin"
    mongo_db: str = "dietary"
    mongo_server_selection_timeout_ms: int = 5000

    # Access-token verification (DPL-102). The Dietary service verifies RS256 tokens minted by the
    # Identity service against its published JWKS; iss/aud must match what Identity issues.
    identity_jwks_url: str = "http://identity:8081/.well-known/jwks.json"
    jwt_issuer: str = "nutriplan-identity"
    jwt_audience: str = "nutriplan"


settings = Settings()
