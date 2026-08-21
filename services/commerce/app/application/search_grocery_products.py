"""COM-403 use case: search grocery products across the enabled providers.

Fans a provider-agnostic :class:`~app.domain.grocery_catalog.GrocerySearchQuery` out to each enabled
grocery provider through the COM-402 anti-corruption layer
(:class:`~app.grocery.adapter.GroceryProviderAdapter`) and merges the results into the set of
providers that can fulfil the search. The endpoint answers "which providers have these products in
this area", so a provider that returns no matching product is dropped from the result.

The fan-out is resilient: a provider that raises
:class:`~app.domain.errors.GroceryProviderUnavailableError` is skipped rather than failing the whole
search (a single flaky provider must not sink the others). COM-407 layers per-provider circuit
breakers, timeouts, and fallback over this same seam.

Ordering and enablement come from the :class:`~app.domain.grocery.GroceryProviderRegistry`
(COM-401), so results follow the configured provider order and a disabled provider is never queried.
An optional ``providers`` filter on the query narrows the fan-out to specific ids (still intersected
with the enabled set).
"""

from __future__ import annotations

from collections.abc import Mapping

from app.domain.errors import GroceryProviderUnavailableError
from app.domain.grocery import GroceryProvider, GroceryProviderRegistry
from app.domain.grocery_catalog import GrocerySearchQuery
from app.grocery.adapter import GroceryProviderAdapter


class SearchGroceryProductsService:
    """Searches enabled grocery providers and reports which ones can fulfil a query (COM-403)."""

    def __init__(
        self,
        registry: GroceryProviderRegistry,
        adapters: Mapping[str, GroceryProviderAdapter],
    ) -> None:
        self._registry = registry
        self._adapters = adapters

    def search(self, query: GrocerySearchQuery) -> tuple[GroceryProvider, ...]:
        """Return the enabled providers (in configured order) that match ``query``.

        A provider is included when its adapter returns at least one product for the query;
        providers that are unavailable (or have no adapter wired) are skipped. When
        ``query.providers`` is non-empty the fan-out is restricted to those ids.
        """
        requested = set(query.providers)
        matches: list[GroceryProvider] = []
        for provider in self._registry.available():
            if requested and provider.id not in requested:
                continue
            adapter = self._adapters.get(provider.id)
            if adapter is None:
                continue
            try:
                result = adapter.search(query)
            except GroceryProviderUnavailableError:
                continue
            if result.products:
                matches.append(provider)
        return tuple(matches)
