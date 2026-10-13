"""The real Redis probe (NTF-101).

Everything else about readiness is unit tested with injected probes; this file is the one
place that opens an actual connection, so the driver wiring itself (URL parsing, timeouts,
ping) is proven rather than assumed.

It needs a live Redis, so it is opt-in via ``NOTIFICATION_TEST_REDIS_URL``: skipped on a
bare local checkout, but a hard failure under ``CI``, where the workflow provides a Redis
service container. A deliberately separate variable from ``NOTIFICATION_REDIS_URL`` so
running the suite against real Redis never changes what the *service* is configured with.
"""

import os

import pytest
import redis

from app.core.config import Settings
from app.core.probes import build_bus_probe, build_redis_probe
from app.core.readiness import FAIL, OK, evaluate_readiness

TEST_REDIS_URL = os.getenv("NOTIFICATION_TEST_REDIS_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not TEST_REDIS_URL and not os.getenv("CI"),
    reason="NOTIFICATION_TEST_REDIS_URL not set (no live Redis available)",
)


def _require_url() -> str:
    if not TEST_REDIS_URL:
        pytest.fail("NOTIFICATION_TEST_REDIS_URL must be set under CI so this suite runs for real")
    return TEST_REDIS_URL


def test_probe_pings_a_live_redis() -> None:
    probe = build_redis_probe(Settings(redis_url=_require_url()))

    assert probe is not None
    probe()  # a live server answers, so this returns without raising


def test_bus_probe_shares_the_datastore_connection() -> None:
    probe = build_bus_probe(Settings(redis_url=_require_url(), event_bus_url=""))

    assert probe is not None
    probe()


def test_unconfigured_redis_has_no_probe() -> None:
    assert build_redis_probe(Settings(redis_url="", event_bus_url="")) is None
    assert build_bus_probe(Settings(redis_url="", event_bus_url="")) is None


def test_probe_raises_for_an_unreachable_server() -> None:
    # Port 1 is reserved and never listening, so this exercises the failure path.
    probe = build_redis_probe(Settings(redis_url="redis://127.0.0.1:1/0"))

    assert probe is not None
    with pytest.raises(redis.exceptions.ConnectionError):
        probe()


def test_readiness_is_ready_against_a_live_redis() -> None:
    settings = Settings(redis_url=_require_url(), push_enabled=False)

    result = evaluate_readiness(
        settings,
        redis_probe=build_redis_probe(settings),
        bus_probe=build_bus_probe(settings),
    )

    assert result.ready is True
    assert result.check("redis").status == OK
    assert result.check("event_bus").status == OK


def test_readiness_fails_against_a_dead_redis() -> None:
    settings = Settings(redis_url="redis://127.0.0.1:1/0", push_enabled=False)

    result = evaluate_readiness(
        settings,
        redis_probe=build_redis_probe(settings),
        bus_probe=build_bus_probe(settings),
    )

    assert result.ready is False
    assert result.check("redis").status == FAIL
