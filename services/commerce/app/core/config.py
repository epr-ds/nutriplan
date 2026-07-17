from decimal import Decimal

from pydantic import SecretStr
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

    # Domain-event bus (COM-109). Order lifecycle events (created/confirmed/status-changed) are
    # appended to a Redis stream that the P5 notification service consumes; leave
    # COMMERCE_EVENT_BUS_URL blank and an in-process publisher is used (correct for dev/CI and a
    # single replica, but does not leave the process).
    event_bus_url: str = ""
    event_stream: str = "commerce.order-events"

    # Payments (COM-201). COMMERCE_PAYMENT_PROVIDER selects the processor (stripe/conekta/fake); the
    # secret key is injected from the vault in production (COM-904) and is a SecretStr so it is
    # masked in logs and reprs and never printed. Leave the provider blank or "fake" for dev/CI. The
    # concrete Stripe/Conekta charge calls arrive in COM-202.
    payment_provider: str = "fake"
    payment_secret_key: SecretStr = SecretStr("")
    stripe_base_url: str = "https://api.stripe.com"
    conekta_base_url: str = "https://api.conekta.io"

    # Payment webhook verification (COM-206). Providers sign each asynchronous settlement webhook
    # (OXXO/SPEI confirm/fail) with a shared secret, separate from the charge key above and injected
    # from the vault in production. The fake provider uses it to verify an HMAC-SHA256 signature
    # over the raw request body in dev/CI and tests.
    payment_webhook_secret: SecretStr = SecretStr("")


settings = Settings()
