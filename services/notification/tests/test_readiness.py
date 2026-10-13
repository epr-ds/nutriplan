"""Readiness evaluation (NTF-101, AC1).

The rules under test:

* an *unconfigured* dependency warns outside production but is fatal in production, so
  dev and CI come up on a bare checkout while a misconfigured prod pod stays out of
  rotation;
* a *configured but unreachable* dependency is fatal everywhere -- that is an outage,
  not a missing local setup;
* the aggregate verdict is "ready unless something hard-fails", so warnings are visible
  without withholding traffic.
"""

import pytest

from app.core.config import Settings
from app.core.readiness import FAIL, OK, WARN, evaluate_readiness

REDIS_URL = "redis://redis:6379/0"
# Deliberately not shaped like a PEM block: the tests only care that a value is present,
# and a realistic header would trip the secret scanner on every commit.
APNS_KEY = "apns-p8"


def _settings(**overrides: object) -> Settings:
    """Build settings without reading the ambient environment."""
    base: dict[str, object] = {
        "environment": "development",
        "redis_url": "",
        "event_bus_url": "",
        "push_enabled": True,
        "fcm_project_id": "",
        "fcm_credentials_json": "",
        "apns_team_id": "",
        "apns_key_id": "",
        "apns_private_key": "",
    }
    base.update(overrides)
    return Settings(**base)


def _boom() -> None:
    raise ConnectionError("connection refused")


def test_bare_development_is_ready_with_warnings() -> None:
    result = evaluate_readiness(_settings())

    assert result.ready is True
    assert {check.name for check in result.checks} == {"redis", "event_bus", "push_providers"}
    assert all(check.status == WARN for check in result.checks)
    assert "non-production" in result.check("redis").detail


def test_bare_production_is_not_ready() -> None:
    result = evaluate_readiness(_settings(environment="production"))

    assert result.ready is False
    assert result.check("redis").status == FAIL
    assert result.check("event_bus").status == FAIL
    assert result.check("push_providers").status == FAIL


def test_configured_and_reachable_is_ready() -> None:
    settings = _settings(
        redis_url=REDIS_URL,
        fcm_project_id="nutriplan",
        fcm_credentials_json='{"type":"service_account"}',
    )

    result = evaluate_readiness(settings, redis_probe=lambda: None, bus_probe=lambda: None)

    assert result.ready is True
    assert all(check.status == OK for check in result.checks)
    assert result.check("push_providers").detail == "fcm configured"


@pytest.mark.parametrize("environment", ["development", "production"])
def test_unreachable_redis_fails_in_every_environment(environment: str) -> None:
    """A configured dependency that will not answer is an outage anywhere."""
    settings = _settings(environment=environment, redis_url=REDIS_URL)

    result = evaluate_readiness(settings, redis_probe=_boom, bus_probe=lambda: None)

    assert result.ready is False
    assert result.check("redis").status == FAIL
    assert "ConnectionError" in result.check("redis").detail


def test_unreachable_bus_fails() -> None:
    settings = _settings(redis_url=REDIS_URL)

    result = evaluate_readiness(settings, redis_probe=lambda: None, bus_probe=_boom)

    assert result.ready is False
    assert result.check("event_bus").status == FAIL


def test_configured_but_unprobed_dependency_is_ok_and_says_so() -> None:
    """No probe means "nothing checked it", which must not masquerade as a live check."""
    result = evaluate_readiness(_settings(redis_url=REDIS_URL))

    assert result.ready is True
    assert result.check("redis").status == OK
    assert "not probed" in result.check("redis").detail


def test_bus_check_names_the_stream_it_consumes() -> None:
    settings = _settings(redis_url=REDIS_URL, order_event_stream="commerce.order-events")

    result = evaluate_readiness(settings, redis_probe=lambda: None, bus_probe=lambda: None)

    assert "commerce.order-events" in result.check("event_bus").detail


def test_bus_inherits_the_datastore_redis() -> None:
    """Configuring only NOTIFICATION_REDIS_URL must satisfy the bus check too."""
    result = evaluate_readiness(_settings(environment="production", redis_url=REDIS_URL))

    assert result.check("event_bus").status == OK


def test_either_push_provider_satisfies_production() -> None:
    settings = _settings(
        environment="production",
        redis_url=REDIS_URL,
        apns_team_id="TEAM123",
        apns_key_id="KEY456",
        apns_private_key=APNS_KEY,
    )

    result = evaluate_readiness(settings)

    assert result.check("push_providers").status == OK
    assert result.check("push_providers").detail == "apns configured"


def test_both_push_providers_are_reported() -> None:
    settings = _settings(
        fcm_project_id="nutriplan",
        fcm_credentials_json='{"type":"service_account"}',
        apns_team_id="TEAM123",
        apns_key_id="KEY456",
        apns_private_key=APNS_KEY,
    )

    result = evaluate_readiness(settings)

    assert result.check("push_providers").detail == "fcm, apns configured"


def test_disabled_push_is_ok_even_in_production() -> None:
    settings = _settings(environment="production", redis_url=REDIS_URL, push_enabled=False)

    result = evaluate_readiness(settings)

    assert result.check("push_providers").status == OK
    assert result.check("push_providers").detail == "push disabled"
    assert result.ready is True


def test_check_lookup_rejects_unknown_names() -> None:
    result = evaluate_readiness(_settings())

    with pytest.raises(KeyError):
        result.check("database")
