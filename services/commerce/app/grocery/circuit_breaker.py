"""Per-provider circuit breakers for the grocery ACL (COM-407).

A grocery provider that is timing out or erroring must not keep costing every request its full
timeout budget. After ``failure_threshold`` consecutive failures that provider's breaker *opens*
and further calls fail fast without touching the network; once ``reset_timeout_seconds`` have
elapsed the breaker admits a single *half-open* probe, which closes the circuit if it succeeds and
re-opens it for another cooldown if it does not.

Breaker state is per provider and lives for the whole process (the registry below is built once in
the composition root), because the adapters themselves are rebuilt per request -- a breaker that
forgot its failure streak that often would never open.

Every state change is reported through :class:`BreakerTelemetry` -- logged in production, captured
in memory in tests -- and the current state of every provider is readable as a
:class:`BreakerSnapshot`, which the readiness probe surfaces (AC3: breaker state is observable).

The clock is injected so the state machine is unit-testable without sleeping, and every mutation is
guarded by a lock because FastAPI runs these synchronous handlers in a thread pool.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

logger = logging.getLogger(__name__)


class BreakerState(StrEnum):
    """The three states of a provider's circuit."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class BreakerPolicy:
    """How readily a provider's circuit trips, and how long it stays open."""

    failure_threshold: int = 5
    reset_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if self.reset_timeout_seconds <= 0:
            raise ValueError("reset_timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class BreakerSnapshot:
    """A point-in-time reading of one provider's circuit, for telemetry and health reporting."""

    provider_id: str
    state: BreakerState
    consecutive_failures: int
    seconds_until_retry: float


@dataclass(frozen=True, slots=True)
class BreakerTransition:
    """One state change, reported to telemetry as it happens."""

    provider_id: str
    from_state: BreakerState
    to_state: BreakerState
    consecutive_failures: int


class BreakerTelemetry(Protocol):
    """Receives every circuit-breaker state change (COM-407 AC3)."""

    def record(self, transition: BreakerTransition) -> None:
        """Record that a provider's circuit moved between states."""
        ...


class InMemoryBreakerTelemetry:
    """Collects transitions in process -- the offline default and the test spy."""

    def __init__(self) -> None:
        self._transitions: list[BreakerTransition] = []
        self._lock = threading.Lock()

    @property
    def transitions(self) -> tuple[BreakerTransition, ...]:
        with self._lock:
            return tuple(self._transitions)

    def record(self, transition: BreakerTransition) -> None:
        with self._lock:
            self._transitions.append(transition)

    def count_into(self, state: BreakerState) -> int:
        """How many transitions moved some provider *into* ``state``."""
        return sum(1 for transition in self.transitions if transition.to_state is state)


class LoggingBreakerTelemetry:
    """Logs every transition: tripping a circuit is a warning, recovering is informational."""

    def record(self, transition: BreakerTransition) -> None:
        level = logging.WARNING if transition.to_state is BreakerState.OPEN else logging.INFO
        logger.log(
            level,
            "Grocery provider %s circuit %s -> %s after %d consecutive failures",
            transition.provider_id,
            transition.from_state,
            transition.to_state,
            transition.consecutive_failures,
        )


class CircuitBreaker:
    """The closed/open/half-open state machine guarding one grocery provider."""

    def __init__(
        self,
        provider_id: str,
        *,
        policy: BreakerPolicy | None = None,
        telemetry: BreakerTelemetry | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._provider_id = provider_id
        self._policy = policy or BreakerPolicy()
        self._telemetry = telemetry
        self._clock = clock
        self._lock = threading.Lock()
        self._state = BreakerState.CLOSED
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def state(self) -> BreakerState:
        with self._lock:
            return self._state

    def allows(self) -> bool:
        """Report whether a call may proceed, promoting a cooled-down circuit to half-open.

        Exactly one probe is admitted per cooldown: while that probe is in flight the circuit is
        already ``HALF_OPEN`` and further calls are refused, so a recovering provider is never
        stampeded by the traffic that tripped it.
        """
        with self._lock:
            if self._state is BreakerState.CLOSED:
                return True
            if self._state is BreakerState.HALF_OPEN:
                return False
            if self._remaining_cooldown() > 0:
                return False
            self._transition_to(BreakerState.HALF_OPEN)
            return True

    def record_success(self) -> None:
        """Forget the failure streak and close the circuit if it was not already closed."""
        with self._lock:
            self._failures = 0
            self._opened_at = None
            if self._state is not BreakerState.CLOSED:
                self._transition_to(BreakerState.CLOSED)

    def record_failure(self) -> None:
        """Count a failure, opening the circuit at the threshold or on a failed half-open probe."""
        with self._lock:
            self._failures += 1
            if self._state is BreakerState.HALF_OPEN:
                self._open()
            elif (
                self._state is BreakerState.CLOSED
                and self._failures >= self._policy.failure_threshold
            ):
                self._open()

    def snapshot(self) -> BreakerSnapshot:
        """Read this provider's current state without changing it."""
        with self._lock:
            return BreakerSnapshot(
                provider_id=self._provider_id,
                state=self._state,
                consecutive_failures=self._failures,
                seconds_until_retry=self._remaining_cooldown(),
            )

    def _open(self) -> None:
        self._opened_at = self._clock()
        self._transition_to(BreakerState.OPEN)

    def _remaining_cooldown(self) -> float:
        if self._state is not BreakerState.OPEN or self._opened_at is None:
            return 0.0
        elapsed = self._clock() - self._opened_at
        return max(0.0, self._policy.reset_timeout_seconds - elapsed)

    def _transition_to(self, state: BreakerState) -> None:
        previous, self._state = self._state, state
        if self._telemetry is not None:
            self._telemetry.record(
                BreakerTransition(
                    provider_id=self._provider_id,
                    from_state=previous,
                    to_state=state,
                    consecutive_failures=self._failures,
                )
            )


class CircuitBreakerRegistry:
    """Holds one :class:`CircuitBreaker` per provider id for the life of the process.

    The grocery adapters are rebuilt on every request, so the breakers cannot live on them: this
    registry is what remembers, between requests, that a provider is unhealthy.
    """

    def __init__(
        self,
        *,
        policy: BreakerPolicy | None = None,
        telemetry: BreakerTelemetry | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._policy = policy or BreakerPolicy()
        self._telemetry = telemetry
        self._clock = clock
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def for_provider(self, provider_id: str) -> CircuitBreaker:
        """Return ``provider_id``'s breaker, creating it on first use."""
        with self._lock:
            breaker = self._breakers.get(provider_id)
            if breaker is None:
                breaker = CircuitBreaker(
                    provider_id,
                    policy=self._policy,
                    telemetry=self._telemetry,
                    clock=self._clock,
                )
                self._breakers[provider_id] = breaker
            return breaker

    def snapshot(self) -> tuple[BreakerSnapshot, ...]:
        """Read every known provider's state, ordered by provider id (COM-407 AC3)."""
        with self._lock:
            breakers = tuple(self._breakers.values())
        return tuple(sorted((b.snapshot() for b in breakers), key=lambda s: s.provider_id))
