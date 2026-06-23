"""Tests for per-user / per-route token quotas and the global kill-switch (AIA-105)."""

import pytest

from app.budget.errors import GlobalBudgetExceededError, QuotaExceededError
from app.budget.guard import TokenBudgetGuard
from app.budget.policy import BudgetPolicy, BudgetScope
from app.kv.memory import InMemoryKeyValueStore

_WINDOW = 86_400


class _Clock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def _guard(store: InMemoryKeyValueStore, **limits: int) -> TokenBudgetGuard:
    return TokenBudgetGuard(store, BudgetPolicy(**limits), namespace="ai:budget")


def test_check_passes_when_under_quota() -> None:
    _guard(InMemoryKeyValueStore(), per_user_tokens=100).check(BudgetScope(user_id="u1"))


def test_user_quota_blocks_after_it_is_spent() -> None:
    store = InMemoryKeyValueStore()
    guard = _guard(store, per_user_tokens=10)
    guard.charge(BudgetScope(user_id="u1"), 10)

    with pytest.raises(QuotaExceededError) as exc:
        guard.check(BudgetScope(user_id="u1"))
    assert exc.value.scope == "user"
    guard.check(BudgetScope(user_id="u2"))  # a different user is unaffected


def test_route_quota_is_independent() -> None:
    store = InMemoryKeyValueStore()
    guard = _guard(store, per_route_tokens=10)
    guard.charge(BudgetScope(route="/ai/recommendations"), 12)

    with pytest.raises(QuotaExceededError) as exc:
        guard.check(BudgetScope(route="/ai/recommendations"))
    assert exc.value.scope == "route"
    guard.check(BudgetScope(route="/ai/analyze-meal"))


def test_zero_limit_never_blocks() -> None:
    store = InMemoryKeyValueStore()
    guard = _guard(store)  # every limit defaults to 0 == unbounded
    guard.charge(BudgetScope(user_id="u1", route="r"), 10_000)
    guard.check(BudgetScope(user_id="u1", route="r"))


def test_global_kill_switch_latches_for_everyone() -> None:
    store = InMemoryKeyValueStore()
    guard = _guard(store, global_tokens=100)
    guard.charge(BudgetScope(user_id="u1"), 100)

    with pytest.raises(GlobalBudgetExceededError):
        guard.check(BudgetScope(user_id="a-different-user"))


def test_window_resets_a_user_quota() -> None:
    clock = _Clock()
    store = InMemoryKeyValueStore(clock=clock)
    guard = _guard(store, per_user_tokens=10)
    guard.charge(BudgetScope(user_id="u1"), 10)
    with pytest.raises(QuotaExceededError):
        guard.check(BudgetScope(user_id="u1"))

    clock.now += _WINDOW + 1
    guard.check(BudgetScope(user_id="u1"))


def test_kill_switch_clears_after_the_window() -> None:
    clock = _Clock()
    store = InMemoryKeyValueStore(clock=clock)
    guard = _guard(store, global_tokens=100)
    guard.charge(BudgetScope(user_id="u1"), 100)
    with pytest.raises(GlobalBudgetExceededError):
        guard.check(BudgetScope(user_id="u1"))

    clock.now += _WINDOW + 1
    guard.check(BudgetScope(user_id="u1"))


def test_charge_ignores_nonpositive_tokens() -> None:
    store = InMemoryKeyValueStore()
    guard = _guard(store, per_user_tokens=10)
    guard.charge(BudgetScope(user_id="u1"), 0)
    guard.charge(BudgetScope(user_id="u1"), -5)
    guard.check(BudgetScope(user_id="u1"))
