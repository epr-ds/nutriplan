"""COM-401 use case: list the grocery providers available for fulfillment.

A thin read-side application service over the :class:`~app.domain.grocery.GroceryProviderRegistry`
policy. It exists so the HTTP layer depends on a use case rather than the registry directly
(matching :class:`~app.application.dark_kitchen_availability.CheckDarkKitchenAvailabilityService`),
leaving room for later stories to enrich the listing (e.g. live health from the circuit breakers in
COM-407) without changing the endpoint.
"""

from __future__ import annotations

from app.domain.grocery import GroceryProvider, GroceryProviderRegistry


class ListGroceryProvidersService:
    """Returns the grocery providers enabled in this environment (COM-401)."""

    def __init__(self, registry: GroceryProviderRegistry) -> None:
        self._registry = registry

    def list_available(self) -> tuple[GroceryProvider, ...]:
        """The enabled providers, in configured order."""
        return self._registry.available()
