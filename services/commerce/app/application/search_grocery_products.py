"""COM-403 use case: search grocery products across the enabled providers.

Fans a provider-agnostic :class:`~app.domain.grocery.GrocerySearchQuery` out to each enabled
grocery provider through the COM-402 anti-corruption layer
(:class:`~app.grocery.adapter.GroceryProviderAdapter`) and merges the results into the set of
providers that can fulfil the search. The endpoint answers "which providers have these products in
this area", so a provider that returns no matching product is dropped from the result.

The fan-out is resilient: a provider that raises
:class:`~app.domain.errors.GroceryProviderUnavailableError` is skipped rather than failing the whole
search (a single flaky provider must not sink the others). COM-407 layers per-provider timeouts and
circuit breakers over this same seam: each adapter is wrapped in
:class:`~app.grocery.resilient.CircuitBreakingGroceryAdapter`, so a provider whose circuit is open
raises that same error immediately -- without a network call -- and is skipped here, which is the
fallback.

COM-409 adds two behaviours over the same seam: an optional response cache (short TTL, shared
across identical searches) and an optional per-provider rate limiter. Both are opt-in dependencies
of the use case, so callers that need the caching/throttling behaviour inject them and the fan-out
above stays a pure function of (registry, adapters, cache, limiter).

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
from app.grocery.cache import SearchResultCache
from app.grocery.ratelimit import ProviderRateLimiter


class SearchGroceryProductsService:
    """Searches enabled grocery providers and reports which ones can fulfil a query (COM-403)."""

    def __init__(
        self,
        registry: GroceryProviderRegistry,
        adapters: Mapping[str, GroceryProviderAdapter],
        *,
        cache: SearchResultCache | None = None,
        rate_limiter: ProviderRateLimiter | None = None,
    ) -> None:
        self._registry = registry
        self._adapters = adapters
        self._cache = cache
        self._rate_limiter = rate_limiter

    def search(self, query: GrocerySearchQuery) -> tuple[GroceryProvider, ...]:
        """Return the enabled providers (in configured order) that match ``query``.

        A provider is included when its adapter returns at least one product for the query;
        providers that are unavailable (or have no adapter wired) are skipped. When
        ``query.providers`` is non-empty the fan-out is restricted to those ids.

        ``cache`` (COM-409) memoizes successful answers per provider for ``ttl_seconds``; an
        identical repeat within the TTL is served from the cache instead of the adapter. A
        ``rate_limiter`` (COM-409) throttles how many provider calls each provider may make; a
        throttled provider is skipped rather than fatal.
        """
        requested = set(query.providers)
        matches: list[GroceryProvider] = []
        for provider in self._registry.available():
            if requested and provider.id not in requested:
                continue
            adapter = self._adapters.get(provider.id)
            if adapter is None:
                continue
            if self._rate_limiter is not None and not self._rate_limiter.acquire(provider.id):
                continue
            result = None
            if self._cache is not None:
                result = self._cache.get(self._cache_key(provider.id, query))
            if result is None:
                try:
                    result = adapter.search(query)
                except GroceryProviderUnavailableError:
                    continue
                if self._cache is not None:
                    self._cache.store(self._cache_key(provider.id, query), result)
            if result.products:
                matches.append(provider)
        return tuple(matches)

    def _cache_key(self, provider_id: str, query: GrocerySearchQuery) -> str:
        items = ",".join(sorted({item.ingredient.strip().lower() for item in query.items}))
        providers = ",".join(sorted(query.providers))
        return f"search:{provider_id}:{query.zip_code}:{items}:{providers}"
