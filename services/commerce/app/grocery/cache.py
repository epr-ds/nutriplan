"""TTL response cache for grocery provider searches (COM-409).

The cross-provider search fan-out (COM-403) re-queries every enabled provider for every search.
For hot ingredients a repeated identical query within a short window is pure waste: cache the
provider answers and serve repeats from memory until the entry expires.

Entries are keyed by ``<provider_id>|<zip>|<items>|<providers>`` and live for a fixed TTL
(default 30s). Lookups are mutex-guarded because FastAPI runs these synchronous handlers in a
thread pool, and every hit is counted both on the cache and on the Prometheus counter that backs
the dashboard / ``search_cache_hits`` alert.
"""

from __future__ import annotations

import threading
import time

from prometheus_client import Counter

from app.domain.grocery_catalog import GrocerySearchResult

commerce_grocery_search_cache_hits_total = Counter(
    "commerce_grocery_search_cache_hits_total",
    "Grocery provider search cache hits.",
)


class SearchResultCache:
    """A small in-process TTL cache for provider search results."""

    def __init__(self, *, ttl_seconds: float = 30.0) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, tuple[float, GrocerySearchResult]] = {}
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> GrocerySearchResult | None:
        """Return the cached result for ``key`` or ``None`` when absent/expired."""
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self.misses += 1
                return None
            expires_at, result = entry
            if expires_at <= now:
                del self._entries[key]
                self.misses += 1
                return None
            self.hits += 1
            commerce_grocery_search_cache_hits_total.inc()
            return result

    def store(self, key: str, result: GrocerySearchResult) -> None:
        """Cache ``result`` under ``key`` with the configured TTL."""
        with self._lock:
            self._entries[key] = (time.monotonic() + self.ttl_seconds, result)
