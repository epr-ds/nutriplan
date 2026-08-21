from decimal import Decimal

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class GroceryProviderSetting(BaseModel):
    """One configured grocery provider (COM-401), mapped to the domain registry in ``deps``.

    ``id`` is the stable machine identifier; ``enabled`` gates whether the provider is offered in
    this environment (per-env enable/disable). The remaining fields are display metadata surfaced on
    ``ProviderResponse``. Override the whole catalogue per environment with a JSON array in
    ``COMMERCE_GROCERY_PROVIDERS``.
    """

    id: str
    name: str
    enabled: bool = True
    logo_url: str | None = None
    estimated_delivery: str | None = None


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

    # Kitchen status webhook verification (COM-303). A dark kitchen signs each fulfilment callback
    # (kitchen.preparing / kitchen.dispatched) with a shared secret, separate from the payment
    # secrets above and injected from the vault in production. Verified as an HMAC-SHA256 signature
    # over the raw request body, exactly like the payment webhook.
    kitchen_webhook_secret: SecretStr = SecretStr("")

    # Dark-kitchen fulfillment (COM-301, COM-302). Coverage is by Mexican postal-code prefix: a
    # delivery postcode is served when it starts with any of these comma-separated prefixes
    # (defaults cover a set of central CDMX delegations). Every serviceable day offers the same
    # comma-separated delivery windows, and each window can hold up to
    # ``dark_kitchen_slot_capacity`` orders per day (COM-302); availability drops a window once
    # that day's bookings reach capacity. The reservation write path that consumes this capacity
    # arrives in COM-304.
    dark_kitchen_service_zip_prefixes: str = "06,01,03,11,14"
    dark_kitchen_time_slots: str = "09:00-11:00,11:00-13:00,13:00-15:00,17:00-19:00,19:00-21:00"
    dark_kitchen_slot_capacity: int = 20

    # Grocery-provider fulfillment (COM-401). The catalogue of grocery delivery providers, in the
    # order they are offered, each with a per-environment ``enabled`` flag. Only enabled providers
    # are surfaced by ``GET /fulfillment/grocery/providers`` and (from COM-403) fanned out to for
    # search. FreshBasket is the one provider live in sandbox for M5; Walmart and Chedraui are
    # defined but disabled until their ◇ adapters land (COM-405/406). Override the whole list per
    # environment with a JSON array in ``COMMERCE_GROCERY_PROVIDERS``.
    grocery_providers: tuple[GroceryProviderSetting, ...] = (
        GroceryProviderSetting(
            id="freshbasket",
            name="FreshBasket",
            enabled=True,
            logo_url="https://cdn.nutriplan.mx/providers/freshbasket.png",
            estimated_delivery="Same day, 1-2 h",
        ),
        GroceryProviderSetting(
            id="walmart",
            name="Walmart Súper",
            enabled=False,
            logo_url="https://cdn.nutriplan.mx/providers/walmart.png",
            estimated_delivery="Same day, 2-4 h",
        ),
        GroceryProviderSetting(
            id="chedraui",
            name="Chedraui",
            enabled=False,
            logo_url="https://cdn.nutriplan.mx/providers/chedraui.png",
            estimated_delivery="Next day",
        ),
    )

    # FreshBasket grocery adapter (COM-404) -- the one grocery provider live in sandbox for M5. Its
    # adapter talks to FreshBasket's REST API at COMMERCE_FRESHBASKET_BASE_URL with a sandbox API
    # key injected from the vault in production (COM-905); the key is a SecretStr so it is masked in
    # logs and reprs and never printed. Leave COMMERCE_FRESHBASKET_API_KEY blank (dev/CI) and the
    # factory falls back to the in-process fake, so grocery search still works end to end without
    # credentials. The HTTP timeout reuses ``http_timeout_seconds``.
    freshbasket_base_url: str = "https://sandbox.freshbasket.mx/api/v1"
    freshbasket_api_key: SecretStr = SecretStr("")


settings = Settings()
