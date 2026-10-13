"""Accepting an optimized draft (AIA-405).

A :class:`~app.optimization.draft.PlanDraft` is a proposal. When the user accepts it,
:class:`PlanDraftAcceptor` commits the proposed plan through the :class:`PlanWriter` port —
re-statused from ``draft`` to a committed ``active`` plan and scoped to the caller's Bearer token
(the same ownership model :class:`~app.optimization.gateway.PlanGateway` uses for reads). The
original plan is never written, so declining a draft leaves the user's plan exactly as it was.

The real adapter (a dietary-service client that persists via ``createMealPlan``/
``updateMealPlanStatus``) lands with the mobile/gateway slices; this ships the port plus an
in-memory adapter so acceptance is exercised fully offline.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from app.optimization.draft import PlanDraft
from app.optimization.plan import OptimizationPlan

ACCEPTED_STATUS = "active"


class PlanWriter(Protocol):
    """Persists a plan on behalf of the caller, returning the stored plan."""

    def save(self, plan: OptimizationPlan, *, token: str) -> OptimizationPlan: ...


class InMemoryPlanWriter:
    """An offline :class:`PlanWriter` keyed by owner token (tests/dev).

    Mirrors :class:`~app.optimization.gateway.InMemoryPlanGateway`: writes are stored per owner
    token, so an accepted plan is only ever visible to the caller that committed it.
    """

    def __init__(self) -> None:
        self._by_owner: dict[str, dict[str, OptimizationPlan]] = {}

    def save(self, plan: OptimizationPlan, *, token: str) -> OptimizationPlan:
        self._by_owner.setdefault(token, {})[plan.id] = plan
        return plan

    def saved(self, plan_id: str, *, token: str) -> OptimizationPlan | None:
        """Read back a persisted plan (test/dev helper)."""
        return self._by_owner.get(token, {}).get(plan_id)


class PlanDraftAcceptor:
    """Commits an accepted optimized draft as the caller's plan."""

    def __init__(self, writer: PlanWriter) -> None:
        self._writer = writer

    def accept(self, draft: PlanDraft, *, token: str) -> OptimizationPlan:
        """Persist the draft's proposed plan as a committed (``active``) plan and return it.

        Only the proposal is written; ``draft.original`` is never mutated or persisted, so the
        commit is the user's explicit, reversible-by-omission choice.
        """
        committed = replace(draft.proposed, status=ACCEPTED_STATUS)
        return self._writer.save(committed, token=token)


def build_plan_draft_acceptor(writer: PlanWriter | None = None) -> PlanDraftAcceptor:
    """Wire the acceptor, defaulting to an in-memory writer until the real adapter lands."""
    return PlanDraftAcceptor(writer=writer or InMemoryPlanWriter())
