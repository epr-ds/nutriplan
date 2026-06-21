from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via IDENTITY_-prefixed environment variables."""

    model_config = SettingsConfigDict(env_prefix="IDENTITY_", env_file=".env", extra="ignore")

    app_name: str = "NutriPlan Identity Service"
    environment: str = "development"

    # Persistence
    database_url: str = "postgresql+psycopg://nutriplan:nutriplan@postgres:5432/identity"

    # JWT signing (RS256). Leave the PEM keys empty in dev to auto-generate an
    # ephemeral keypair; inject real keys from the secrets manager in stage/prod (IDN-803).
    jwt_private_key: str = ""
    jwt_public_key: str = ""
    jwt_kid: str = "nutriplan-dev"
    jwt_issuer: str = "nutriplan-identity"
    jwt_audience: str = "nutriplan"
    access_token_ttl_seconds: int = 900  # 15 minutes
    refresh_token_ttl_seconds: int = 1_209_600  # 14 days

    # Login throttling (IDN-103)
    login_max_failed_attempts: int = 5
    login_lockout_seconds: int = 900  # 15 minutes

    # Per-IP rate limiting (IDN-106), 60-second window
    rate_limit_enabled: bool = True
    rate_limit_default_per_minute: int = 120
    rate_limit_auth_per_minute: int = 20

    # OAuth providers (IDN-201/202/203): comma-separated accepted audiences (client IDs)
    google_client_ids: str = ""
    apple_client_ids: str = ""
    facebook_client_ids: str = ""

    # Avatar object storage (IDN-304). S3-compatible (MinIO in dev). The endpoint is the one
    # used to *sign* presigned URLs, so it must be reachable by the client (browser/mobile).
    s3_endpoint_url: str = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_access_key: str = "nutriplan"
    s3_secret_key: str = "nutriplan-secret"
    avatar_bucket: str = "avatars"
    avatar_upload_ttl_seconds: int = 900  # 15 minutes
    avatar_allowed_content_types: str = "image/jpeg,image/png,image/webp"


settings = Settings()
