"""Readiness evaluation for the AI service (AIA-101).

Liveness (`/health`) answers "is the process up?"; readiness (`/health/ready`)
answers "can it actually serve AI traffic?". The two are deliberately separate so
an orchestrator restarts a *dead* pod but merely withholds traffic from a *live but
unconfigured* one.

The evaluation is a pure function of :class:`Settings` so it is trivially unit
tested across environments. It is environment-aware: outside production a missing
dependency degrades to a non-fatal ``warn`` (dev/CI still come up and the non-LLM
surface stays usable), while in production it is a hard ``fail`` that takes the pod
out of rotation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings

OK = "ok"
WARN = "warn"
FAIL = "fail"


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


def evaluate_readiness(settings: Settings) -> Readiness:
    """Evaluate every readiness check; ready unless some check hard-``fail``s."""
    checks = (_llm_provider_check(settings),)
    ready = all(check.status != FAIL for check in checks)
    return Readiness(ready=ready, checks=checks)


def _llm_provider_check(settings: Settings) -> CheckResult:
    """Readiness depends on the LLM provider being configured to serve recommendations."""
    if settings.llm_configured:
        return CheckResult("llm_provider", OK, f"{settings.llm_provider} configured")
    if settings.is_production:
        return CheckResult("llm_provider", FAIL, "LLM API key missing")
    return CheckResult("llm_provider", WARN, "LLM API key not set (non-production)")
