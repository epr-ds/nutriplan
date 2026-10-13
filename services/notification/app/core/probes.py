"""Reachability probes for the service's configured dependencies (NTF-101).

Readiness is a pure function of configuration plus these probes, which are the only
place that opens a real connection. They are deliberately thin: a probe answers "can I
reach it right now?" and nothing else. The Redis *store* -- keys, models, TTLs -- is
NTF-102's concern and is not preempted here.

Each probe gets its own short-lived client with a tight timeout so a hung dependency
cannot hold the readiness endpoint open; an orchestrator polling ``/health/ready``
must always get a prompt answer, even a bad one.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.config import Settings
from app.core.config import settings as default_settings

Probe = Callable[[], None]

PROBE_TIMEOUT_SECONDS = 2.0


def build_redis_probe(settings: Settings | None = None) -> Probe | None:
    """Return a probe that pings the datastore, or ``None`` when Redis is unconfigured.

    ``None`` means "nothing to probe" rather than "unreachable" -- the readiness rules
    decide whether an unconfigured dependency is a warning or fatal.
    """
    settings = settings or default_settings
    if not settings.redis_configured:
        return None
    return _ping(settings.redis_url.strip())


def build_bus_probe(settings: Settings | None = None) -> Probe | None:
    """Return a probe that pings the event bus, or ``None`` when it is unconfigured."""
    settings = settings or default_settings
    url = settings.effective_event_bus_url
    if not url:
        return None
    return _ping(url)


def _ping(url: str) -> Probe:
    """Build a probe that opens a Redis connection to ``url`` and pings it."""

    def probe() -> None:
        # Imported lazily so the module stays importable (and unit tests stay fast)
        # without the driver having to connect to anything at import time.
        import redis

        client = redis.Redis.from_url(
            url,
            socket_connect_timeout=PROBE_TIMEOUT_SECONDS,
            socket_timeout=PROBE_TIMEOUT_SECONDS,
        )
        try:
            client.ping()
        finally:
            client.close()

    return probe
