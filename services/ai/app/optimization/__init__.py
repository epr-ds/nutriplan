"""Plan-optimization use case (AIA-401+) — see :mod:`app.optimization.service`."""

from __future__ import annotations

from app.optimization.commands import OptimizationGoal, OptimizePlanCommand
from app.optimization.gateway import InMemoryPlanGateway, PlanGateway
from app.optimization.plan import (
    NutritionTargets,
    OptimizationMeal,
    OptimizationPlan,
    PlanNutrition,
    PlanNutritionSummary,
)
from app.optimization.service import PlanOptimizationService, build_plan_optimization_service

__all__ = [
    "InMemoryPlanGateway",
    "NutritionTargets",
    "OptimizationGoal",
    "OptimizationMeal",
    "OptimizationPlan",
    "OptimizePlanCommand",
    "PlanGateway",
    "PlanNutrition",
    "PlanNutritionSummary",
    "PlanOptimizationService",
    "build_plan_optimization_service",
]
