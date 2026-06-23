"""Token budgets, quotas, and a global kill-switch for the AI service (AIA-105).

LLM calls cost money, so this package keeps them bounded: :class:`~app.budget.guard.\
TokenBudgetGuard` enforces per-user and per-route token quotas over a rolling window
(AC2) and latches a global kill-switch once the overall budget is spent (AC3), refusing
further calls until the window rolls off. Counters live behind the
:class:`~app.kv.store.KeyValueStore` port, so the same logic runs against Redis in
production and an in-process store in tests.
"""

from app.budget.errors import BudgetError, GlobalBudgetExceededError, QuotaExceededError
from app.budget.factory import build_token_budget_guard
from app.budget.guard import TokenBudgetGuard
from app.budget.policy import BudgetPolicy, BudgetScope

__all__ = [
    "BudgetError",
    "BudgetPolicy",
    "BudgetScope",
    "GlobalBudgetExceededError",
    "QuotaExceededError",
    "TokenBudgetGuard",
    "build_token_budget_guard",
]
