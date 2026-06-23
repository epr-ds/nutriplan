"""Errors raised when a request would exceed a token budget (AIA-105, AC2 + AC3).

These are refusals, not failures: the request never reached the provider because a quota
was already spent or the global kill-switch was tripped. They carry the limit and the
amount used so a route can answer ``429`` with a useful ``Retry-After``-style detail.
"""

from __future__ import annotations


class BudgetError(Exception):
    """Base class for a request refused on budget grounds."""


class QuotaExceededError(BudgetError):
    """A per-user or per-route token quota for the current window is exhausted."""

    def __init__(self, message: str, *, scope: str, limit: int, used: int) -> None:
        super().__init__(message)
        self.scope = scope
        self.limit = limit
        self.used = used


class GlobalBudgetExceededError(BudgetError):
    """The global token budget is spent; the kill-switch is latched for the window."""

    def __init__(self, message: str, *, limit: int, used: int) -> None:
        super().__init__(message)
        self.limit = limit
        self.used = used
