"""Readiness evaluation for the Notification service (NTF-101).

Liveness (``/health``) answers "is the process up?"; readiness (``/health/ready``)
answers "can it actually do its job?". The two are deliberately separate so an
orchestrator restarts a *dead* pod but merely withholds traffic from a *live but
unconfigured* one.

The evaluation is a pure function of :class:`Settings` plus optional injected probes,
so every branch is unit testable without a server running. It is environment-aware:
outside production an unconfigured dependency degrades to a non-fatal ``warn`` (dev and
CI still come up), while in production it is a hard ``fail`` that takes the pod out of
rotation. A dependency that *is* configured but unreachable always fails -- that is a
real outage in any environment, not a missing local setup.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings

OK = "ok"
WARN = "warn"
FAIL = "fail"

Probe = Callable[[], None]
"""Contacts a dependency and returns normally, or raises to signal it is unreachable."""


@dataclass(frozen=True)
class CheckResult:
    """The outcome of a single named readiness check."""

    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class Readiness:
    """The aggregate readiness verdict plus the individual checks behind it."""

    ready: bool
    checks: tuple[CheckResult, ...]

    def check(self, name: str) -> CheckResult:
        """Return the check with ``name`` (raises ``KeyError`` if absent)."""
        for result in self.checks:
            if result.name == name:
                return result
        raise KeyError(name)


def evaluate_readiness(
    settings: Settings,
    *,
    redis_probe: Probe | None = None,
    bus_probe: Probe | None = None,
) -> Readiness:
    """Evaluate every readiness check; ready unless some check hard-``fail``s."""
    checks = (
        _redis_check(settings, redis_probe),
        _event_bus_check(settings, bus_probe),
        _push_providers_check(settings),
    )
    ready = all(check.status != FAIL for check in checks)
    return Readiness(ready=ready, checks=checks)


def _redis_check(settings: Settings, probe: Probe | None) -> CheckResult:
    """Readiness depends on the datastore that holds notifications and read-state."""
    if not settings.redis_configured:
        return _missing(settings, "redis", "Redis URL not set")
    return _probe(probe, "redis", "reachable")


def _event_bus_check(settings: Settings, probe: Probe | None) -> CheckResult:
    """Readiness depends on the bus: no bus means no events, so nothing to notify about."""
    if not settings.event_bus_configured:
        return _missing(settings, "event_bus", "event bus URL not set")
    return _probe(probe, "event_bus", f"consuming {settings.order_event_stream}")


def _push_providers_check(settings: Settings) -> CheckResult:
    """Report which push transports are usable; unconfigured push is fatal in production."""
    if not settings.push_enabled:
        return CheckResult("push_providers", OK, "push disabled")
    configured = [
        name
        for name, ok in (("fcm", settings.fcm_configured), ("apns", settings.apns_configured))
        if ok
    ]
    if configured:
        return CheckResult("push_providers", OK, f"{', '.join(configured)} configured")
    return _missing(settings, "push_providers", "no push provider credentials")


def _missing(settings: Settings, name: str, detail: str) -> CheckResult:
    """A dependency that was never configured: fatal in production, tolerated elsewhere."""
    if settings.is_production:
        return CheckResult(name, FAIL, detail)
    return CheckResult(name, WARN, f"{detail} (non-production)")


def _probe(probe: Probe | None, name: str, detail: str) -> CheckResult:
    """Run a reachability probe for a configured dependency; any raise is a hard failure."""
    if probe is None:
        return CheckResult(name, OK, f"{detail} (not probed)")
    try:
        probe()
    except Exception as exc:
        return CheckResult(name, FAIL, f"unreachable: {exc.__class__.__name__}")
    return CheckResult(name, OK, detail)
