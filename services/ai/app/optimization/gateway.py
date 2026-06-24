"""The port for loading a caller-owned meal plan (AIA-401).

The AI service does not own meal plans — they live in the dietary service. A :class:`PlanGateway`
abstracts "fetch the plan with this id, on behalf of the caller holding this Bearer token". The
real adapter (a dietary-service HTTP client that forwards the token, so the dietary service enforces
ownership and returns ``404`` for someone else's plan) lands with plan loading in AIA-402; this
slice ships the port plus an in-memory adapter so the route and its tests run fully offline.

Ownership is expressed in the port's contract: ``get_plan`` returns the plan only when it exists and
belongs to the caller, and ``None`` otherwise. Not-found and not-owned are deliberately
indistinguishable, so the endpoint can map both to ``404`` without leaking which plans exist.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol

from app.optimization.plan import OptimizationPlan


class PlanGateway(Protocol):
    """Loads a meal plan owned by the caller, or ``None`` when absent or not theirs."""

    def get_plan(self, plan_id: str, *, token: str) -> OptimizationPlan | None: ...


class InMemoryPlanGateway:
    """An offline :class:`PlanGateway` keyed by owner token (tests/dev).

    Plans are stored per owner token, so a plan is only returned to the caller that owns it — the
    same guarantee the real dietary-service adapter gets for free by forwarding the token.
    """

    def __init__(self, plans: Mapping[str, Iterable[OptimizationPlan]] | None = None) -> None:
        self._by_owner: dict[str, dict[str, OptimizationPlan]] = {}
        for owner, owned in (plans or {}).items():
            for plan in owned:
                self.add(plan, owner=owner)

    def add(self, plan: OptimizationPlan, *, owner: str) -> None:
        """Seed a plan as owned by ``owner``."""
        self._by_owner.setdefault(owner, {})[plan.id] = plan

    def get_plan(self, plan_id: str, *, token: str) -> OptimizationPlan | None:
        return self._by_owner.get(token, {}).get(plan_id)
