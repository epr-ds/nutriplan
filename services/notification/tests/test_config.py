"""Configuration surface for the Notification service (NTF-101, AC2).

The three dependency groups the acceptance criteria name -- Redis, the bus, and the push
providers -- must all be environment-driven, and the secrets among them must never leak
into a log line or a repr.
"""

from pydantic import SecretStr

from app.core.config import Settings


def test_defaults_are_dev_friendly() -> None:
    settings = Settings()

    assert settings.app_name == "NutriPlan Notification Service"
    assert settings.environment == "development"
    assert settings.is_production is False
    # Nothing is wired by default, so a fresh checkout boots with no infrastructure.
    assert settings.redis_configured is False
    assert settings.event_bus_configured is False


def test_redis_group_is_env_driven(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_REDIS_URL", "redis://cache:6379/2")
    monkeypatch.setenv("NOTIFICATION_REDIS_NAMESPACE", "ntf-stage")
    monkeypatch.setenv("NOTIFICATION_FEED_TTL_SECONDS", "604800")
    monkeypatch.setenv("NOTIFICATION_FEED_MAX_ENTRIES", "250")

    settings = Settings()

    assert settings.redis_url == "redis://cache:6379/2"
    assert settings.redis_namespace == "ntf-stage"
    assert settings.feed_ttl_seconds == 604_800
    assert settings.feed_max_entries == 250
    assert settings.redis_configured is True


def test_bus_group_is_env_driven(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_EVENT_BUS_URL", "redis://bus:6379/0")
    monkeypatch.setenv("NOTIFICATION_ORDER_EVENT_STREAM", "commerce.order-events")
    monkeypatch.setenv("NOTIFICATION_CONSUMER_GROUP", "notification-stage")
    monkeypatch.setenv("NOTIFICATION_EVENT_MAX_DELIVERY_ATTEMPTS", "3")

    settings = Settings()

    assert settings.effective_event_bus_url == "redis://bus:6379/0"
    assert settings.consumer_group == "notification-stage"
    assert settings.event_max_delivery_attempts == 3


def test_bus_defaults_to_the_commerce_order_stream() -> None:
    """The stream name has to match what Commerce publishes to (COM-109)."""
    assert Settings().order_event_stream == "commerce.order-events"


def test_bus_falls_back_to_the_datastore_redis(monkeypatch) -> None:
    """One Redis backs both today; splitting them stays a config change, not a code change."""
    monkeypatch.setenv("NOTIFICATION_REDIS_URL", "redis://shared:6379/0")

    settings = Settings()

    assert settings.event_bus_url == ""
    assert settings.effective_event_bus_url == "redis://shared:6379/0"
    assert settings.event_bus_configured is True


def test_explicit_bus_url_wins_over_the_datastore(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_REDIS_URL", "redis://shared:6379/0")
    monkeypatch.setenv("NOTIFICATION_EVENT_BUS_URL", "redis://dedicated-bus:6379/1")

    assert Settings().effective_event_bus_url == "redis://dedicated-bus:6379/1"


def test_push_providers_are_env_driven(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_FCM_PROJECT_ID", "nutriplan-prod")
    monkeypatch.setenv("NOTIFICATION_FCM_CREDENTIALS_JSON", '{"type":"service_account"}')

    settings = Settings()

    assert settings.fcm_configured is True
    assert settings.apns_configured is False
    # Either provider alone is enough: a single-platform environment is still usable.
    assert settings.push_configured is True


def test_apns_needs_team_key_and_private_key(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_APNS_TEAM_ID", "TEAM123")
    monkeypatch.setenv("NOTIFICATION_APNS_KEY_ID", "KEY456")

    # Two of three: still not callable.
    assert Settings().apns_configured is False

    monkeypatch.setenv("NOTIFICATION_APNS_PRIVATE_KEY", "apns-p8")
    assert Settings().apns_configured is True


def test_disabling_push_satisfies_the_provider_requirement(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_PUSH_ENABLED", "false")

    settings = Settings()

    assert settings.push_enabled is False
    assert settings.push_configured is True


def test_push_credentials_are_masked() -> None:
    """Credentials must not leak through a repr into a log line or a crash report."""
    secret = "super-secret-service-account"  # gitleaks:allow
    settings = Settings(fcm_credentials_json=SecretStr(secret), apns_private_key=SecretStr(secret))

    assert secret not in repr(settings)
    assert secret not in str(settings.fcm_credentials_json)
    assert settings.fcm_credentials_json.get_secret_value() == secret


def test_production_is_detected_case_insensitively(monkeypatch) -> None:
    for value in ("production", "PRODUCTION", " prod "):
        monkeypatch.setenv("NOTIFICATION_ENVIRONMENT", value)
        assert Settings().is_production is True

    for value in ("development", "test", "staging"):
        monkeypatch.setenv("NOTIFICATION_ENVIRONMENT", value)
        assert Settings().is_production is False


def test_identity_verification_matches_what_identity_issues() -> None:
    settings = Settings()

    assert settings.jwt_issuer == "nutriplan-identity"
    assert settings.jwt_audience == "nutriplan"
    assert settings.identity_jwks_url.endswith("/.well-known/jwks.json")
