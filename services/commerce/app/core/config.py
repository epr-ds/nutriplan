from decimal import Decimal

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

    # Access-token verification (COM-102). Commerce is a resource server: it verifies RS256 tokens
    # minted by Identity against its published JWKS; iss/aud must match what Identity issues.
    identity_jwks_url: str = "http://identity:8081/.well-known/jwks.json"
    jwt_issuer: str = "nutriplan-identity"
    jwt_audience: str = "nutriplan"

    # Meal-plan lookups (COM-102) resolve against the Dietary service over HTTP.
    dietary_base_url: str = "http://dietary:8082"
    http_timeout_seconds: float = 5.0

    # Pricing engine (COM-103). Dietary carries no prices, so items are priced here by a per-serving
    # rate keyed on meal type (with a default fallback for unknown types). Amounts are MXN.
    price_per_serving_breakfast: Decimal = Decimal("45.00")
    price_per_serving_lunch: Decimal = Decimal("75.00")
    price_per_serving_dinner: Decimal = Decimal("85.00")
    price_per_serving_snack: Decimal = Decimal("30.00")
    price_per_serving_default: Decimal = Decimal("60.00")

    # Delivery fees are flat per fulfillmentType; an order whose subtotal reaches the free-delivery
    # threshold ships free. Pickup is always free.
    delivery_fee_dark_kitchen: Decimal = Decimal("35.00")
    delivery_fee_grocery_delivery: Decimal = Decimal("49.00")
    delivery_fee_pickup: Decimal = Decimal("0.00")
    free_delivery_threshold: Decimal = Decimal("500.00")


settings = Settings()
