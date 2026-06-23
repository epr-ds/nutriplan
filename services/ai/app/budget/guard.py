"""Enforce per-user / per-route token quotas and a global kill-switch (AIA-105).

The guard wraps the shared counter store and is consulted around a completion: :meth:`check`
is the pre-call gate that refuses a request whose window quota is already spent, and
:meth:`charge` records the tokens a successful call actually used. Because the true cost is
only known after the call, a single request may push a counter over its limit -- the next
one in that window is then refused (a soft quota).

The global budget doubles as a **kill-switch**: when :meth:`charge` carries total usage past
``global_tokens`` it latches a flag for the rest of the window, so every caller -- not just
the one that tipped it over -- is turned away until the window rolls off. Counters expire via
the store's TTL, which makes the window reset itself with no sweeper.
"""

from __future__ import annotations

from app.budget.errors import GlobalBudgetExceededError, QuotaExceededError
from app.budget.policy import BudgetPolicy, BudgetScope
from app.kv.store import KeyValueStore


class TokenBudgetGuard:
    """Gate completions on token budgets backed by an expiring counter store."""

    def __init__(
        self,
        store: KeyValueStore,
        policy: BudgetPolicy,
        *,
        namespace: str = "ai:budget",
    ) -> None:
        self._store = store
        self._policy = policy
        self._namespace = namespace

    def check(self, scope: BudgetScope) -> None:
        """Refuse the request if a global, per-user, or per-route quota is exhausted."""
        used_global = self._used(self._global_key())
        if self._killswitch_on() or self._over(self._policy.global_tokens, used_global):
            raise GlobalBudgetExceededError(
                "global AI token budget exceeded; requests are paused",
                limit=self._policy.global_tokens,
                used=used_global,
            )
        self._check_quota("user", self._policy.per_user_tokens, self._user_key(scope))
        self._check_quota("route", self._policy.per_route_tokens, self._route_key(scope))

    def charge(self, scope: BudgetScope, tokens: int) -> None:
        """Record ``tokens`` against every applicable counter, tripping the kill-switch."""
        if tokens <= 0:
            return
        ttl = self._policy.window_seconds
        for key in (self._user_key(scope), self._route_key(scope)):
            if key is not None:
                self._store.increment(key, tokens, ttl_seconds=ttl)
        total = self._store.increment(self._global_key(), tokens, ttl_seconds=ttl)
        if self._over(self._policy.global_tokens, total):
            self._store.set(self._killswitch_key(), "1", ttl_seconds=ttl)

    def _check_quota(self, scope_name: str, limit: int, key: str | None) -> None:
        if key is None:
            return
        used = self._used(key)
        if self._over(limit, used):
            raise QuotaExceededError(
                f"{scope_name} AI token quota exceeded",
                scope=scope_name,
                limit=limit,
                used=used,
            )

    @staticmethod
    def _over(limit: int, used: int) -> bool:
        return limit > 0 and used >= limit

    def _used(self, key: str) -> int:
        raw = self._store.get(key)
        if raw is None:
            return 0
        try:
            return int(raw)
        except ValueError:  # pragma: no cover - counters are only ever written as ints
            return 0

    def _killswitch_on(self) -> bool:
        return self._store.get(self._killswitch_key()) is not None

    def _killswitch_key(self) -> str:
        return f"{self._namespace}:killswitch"

    def _global_key(self) -> str:
        return f"{self._namespace}:global"

    def _user_key(self, scope: BudgetScope) -> str | None:
        if self._policy.per_user_tokens <= 0 or scope.user_id is None:
            return None
        return f"{self._namespace}:user:{scope.user_id}"

    def _route_key(self, scope: BudgetScope) -> str | None:
        if self._policy.per_route_tokens <= 0 or scope.route is None:
            return None
        return f"{self._namespace}:route:{scope.route}"
