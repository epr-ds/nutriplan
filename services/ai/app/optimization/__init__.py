"""Plan-optimization use case (AIA-401+) — see :mod:`app.optimization.service`."""

from __future__ import annotations

from app.optimization.baseline import (
    BaselineDirection,
    BaselineMetric,
    baseline_for,
    measure_metric,
)
from app.optimization.commands import OptimizationGoal, OptimizePlanCommand
from app.optimization.gateway import InMemoryPlanGateway, PlanGateway
from app.optimization.plan import (
    NutritionTargets,
    OptimizationMeal,
    OptimizationPlan,
    PlanNutrition,
    PlanNutritionSummary,
)
from app.optimization.result import OptimizationOutcome
from app.optimization.service import PlanOptimizationService, build_plan_optimization_service

__all__ = [
    "BaselineDirection",
    "BaselineMetric",
    "InMemoryPlanGateway",
    "NutritionTargets",
    "OptimizationGoal",
    "OptimizationMeal",
    "OptimizationOutcome",
    "OptimizationPlan",
    "OptimizePlanCommand",
    "PlanGateway",
    "PlanNutrition",
    "PlanNutritionSummary",
    "PlanOptimizationService",
    "baseline_for",
    "build_plan_optimization_service",
    "measure_metric",
]
