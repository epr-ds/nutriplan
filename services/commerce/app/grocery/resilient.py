"""Fail fast on a grocery provider whose circuit is open (COM-407).

Decorates any :class:`~app.grocery.adapter.GroceryProviderAdapter` with that provider's
:class:`~app.grocery.circuit_breaker.CircuitBreaker`, mirroring the wrapper style of
:class:`~app.events.resilient.ResilientEventPublisher`. Because the decorator satisfies the same
port, nothing above the ACL knows it is there.

While the circuit is open the call is refused *without touching the network* and reported as a
:class:`~app.domain.errors.GroceryProviderUnavailableError` -- the same domain error a genuinely
unreachable provider raises -- so the COM-403 fan-out already skips that provider and answers from
the healthy ones (AC2: an open circuit degrades to a fallback rather than an error).

Only :class:`~app.domain.errors.GroceryProviderUnavailableError` counts as a failure: it is the one
condition the ACL normalises every transport, timeout, and upstream fault onto, so it means "the
provider is unhealthy". Any other exception is a bug on our side of the boundary and propagates
untouched rather than tripping a provider's circuit.
"""

from __future__ import annotations

from collections.abc import Callable

from app.domain.errors import GroceryProviderUnavailableError
from app.domain.grocery_catalog import (
    GroceryOrderPlacement,
    GroceryOrderRequest,
    GroceryOrderStatus,
    GrocerySearchQuery,
    GrocerySearchResult,
)
from app.grocery.adapter import GroceryProviderAdapter
from app.grocery.circuit_breaker import CircuitBreaker


class CircuitBreakingGroceryAdapter:
    """Wrap a grocery adapter so an unhealthy provider fails fast instead of being retried."""

    def __init__(self, inner: GroceryProviderAdapter, breaker: CircuitBreaker) -> None:
        self._inner = inner
        self._breaker = breaker

    @property
    def provider_id(self) -> str:
        return self._inner.provider_id

    @property
    def breaker(self) -> CircuitBreaker:
        """The provider's breaker, exposed so its state can be read (COM-407 AC3)."""
        return self._breaker

    def search(self, query: GrocerySearchQuery) -> GrocerySearchResult:
        return self._guard(lambda: self._inner.search(query))

    def place_order(self, request: GroceryOrderRequest) -> GroceryOrderPlacement:
        return self._guard(lambda: self._inner.place_order(request))

    def get_order_status(self, external_order_id: str) -> GroceryOrderStatus:
        return self._guard(lambda: self._inner.get_order_status(external_order_id))

    def _guard[T](self, call: Callable[[], T]) -> T:
        if not self._breaker.allows():
            raise GroceryProviderUnavailableError(
                self.provider_id,
                f"grocery provider {self.provider_id} is unavailable (circuit open)",
            )
        try:
            result = call()
        except GroceryProviderUnavailableError:
            self._breaker.record_failure()
            raise
        self._breaker.record_success()
        return result
