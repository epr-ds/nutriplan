"""The application command for the plan-optimization use case (AIA-401).

The route maps its validated HTTP request onto an :class:`OptimizePlanCommand`. The command's
vocabulary (:class:`OptimizationGoal`) is deliberately separate from the API-layer enum in
``app/api/schemas.py`` (identical string values): the wire shape can evolve independently of how the
service consumes the request, mirroring the recommendation/analysis slices.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OptimizationGoal(StrEnum):
    """What the caller wants the optimization to prioritize (``OptimizePlanRequest.goal``)."""

    BALANCE_MACROS = "balance_macros"
    INCREASE_PROTEIN = "increase_protein"
    REDUCE_CALORIES = "reduce_calories"
    INCREASE_SATISFACTION = "increase_satisfaction"


@dataclass(frozen=True, slots=True)
class OptimizePlanCommand:
    """A validated request to optimize one plan toward an optional goal.

    ``plan_id`` identifies the plan to load (ownership is enforced when it is fetched). ``goal`` is
    optional — the contract only requires ``planId`` — and steers the optimization in AIA-403+.
    """

    plan_id: str
    goal: OptimizationGoal | None = None
