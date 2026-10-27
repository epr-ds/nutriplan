"""COM-409: grocery provider response caching + per-provider rate limiting."""

from __future__ import annotations

from app.application.search_grocery_products import SearchGroceryProductsService
from app.domain.grocery import GroceryProvider, GroceryProviderRegistry
from app.domain.grocery_catalog import GrocerySearchItem, GrocerySearchQuery
from app.grocery.cache import SearchResultCache
from app.grocery.fake import FakeGroceryProviderAdapter
from app.grocery.ratelimit import ProviderRateLimiter

FRESH = GroceryProvider(id="freshbasket", name="FreshBasket", enabled=True)


class CountingAdapter(FakeGroceryProviderAdapter):
    """Fake adapter that counts how many times its search was actually served."""

    def __init__(self, provider_id: str = "freshbasket", *, catalogue=None) -> None:
        super().__init__(provider_id, catalogue=catalogue)
        self.calls = 0

    def search(self, query) -> object:  # noqa: ANN201 - test stub
        self.calls += 1
        return super().search(query)


def _query(*ingredients: str) -> GrocerySearchQuery:
    return GrocerySearchQuery(
        zip_code="06700",
        items=tuple(GrocerySearchItem(ingredient=name) for name in ingredients),
    )


def _adapter() -> CountingAdapter:
    return CountingAdapter(
        "freshbasket",
        catalogue={
            "milk": [
                {
                    "id": "fb-milk-1l",
                    "title": "Milk 1L",
                    "price_cents": 2000,
                    "currency": "MXN",
                    "availability": "in_stock",
                },
            ],
        },
    )


def test_repeated_identical_search_is_served_from_cache():
    adapter = _adapter()
    service = SearchGroceryProductsService(
        GroceryProviderRegistry(providers=(FRESH,)),
        {"freshbasket": adapter},
        cache=SearchResultCache(ttl_seconds=30.0),
    )
    first = service.search(_query("milk"))
    second = service.search(_query("milk"))
    assert adapter.calls == 1
    assert second == first


def test_cache_hit_is_reported():
    cache = SearchResultCache(ttl_seconds=30.0)
    adapter = _adapter()
    service = SearchGroceryProductsService(
        GroceryProviderRegistry(providers=(FRESH,)),
        {"freshbasket": adapter},
        cache=cache,
    )
    service.search(_query("milk"))
    service.search(_query("milk"))
    assert cache.hits >= 1


def test_provider_rate_limit_blocks_excess_searches():
    adapter = _adapter()
    limiter = ProviderRateLimiter(capacity=1, refill_seconds=30.0)
    service = SearchGroceryProductsService(
        GroceryProviderRegistry(providers=(FRESH,)),
        {"freshbasket": adapter},
        cache=None,
        rate_limiter=limiter,
    )
    service.search(_query("milk"))
    second = service.search(_query("milk"))
    assert adapter.calls == 1
    assert second == ()
