"""Build a :class:`~app.budget.guard.TokenBudgetGuard` from configuration."""

from __future__ import annotations

from app.budget.guard import TokenBudgetGuard
from app.budget.policy import BudgetPolicy
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.kv.factory import build_key_value_store
from app.kv.store import KeyValueStore


def build_token_budget_guard(
    settings: Settings | None = None,
    store: KeyValueStore | None = None,
) -> TokenBudgetGuard:
    """Construct the budget guard, sharing a store with the cache when given."""
    settings = settings or default_settings
    store = store or build_key_value_store(settings)
    policy = BudgetPolicy(
        per_user_tokens=settings.budget_per_user_tokens,
        per_route_tokens=settings.budget_per_route_tokens,
        global_tokens=settings.budget_global_tokens,
        window_seconds=settings.budget_window_seconds,
    )
    return TokenBudgetGuard(store, policy, namespace=settings.budget_namespace)
