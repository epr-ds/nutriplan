"""Value objects describing *who* is spending and *how much* they may spend.

:class:`BudgetScope` names the caller for a single completion (a user, a route, or both);
:class:`BudgetPolicy` carries the limits and the window they reset over. A limit of ``0``
means "unbounded" for that dimension, which keeps quotas opt-in: an unset limit never
blocks anyone. Both are frozen so they are safe to share across requests.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BudgetScope:
    """Identifies the principal a completion is billed to."""

    user_id: str | None = None
    route: str | None = None


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    """Token limits per window; ``0`` disables that dimension."""

    per_user_tokens: int = 0
    per_route_tokens: int = 0
    global_tokens: int = 0
    window_seconds: int = 86_400
