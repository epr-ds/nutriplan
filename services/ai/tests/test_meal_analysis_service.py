"""Unit tests for the meal-analysis application service (AIA-301).

AIA-301 ships the validated transport seam: the service accepts a :class:`MealAnalysisCommand` and
returns a :class:`MealAnalysis`. Nutrition estimation and warnings arrive in AIA-302, so for now the
analysis it returns is empty regardless of input. These tests pin that contract.
"""

from __future__ import annotations

from app.analysis.commands import MealAnalysisCommand, MealIngredient
from app.analysis.result import MealAnalysis
from app.analysis.service import MealAnalysisService, build_meal_analysis_service


def test_analyze_returns_an_empty_analysis_for_now() -> None:
    service = MealAnalysisService()

    result = service.analyze(MealAnalysisCommand(description="Oatmeal with banana"))

    assert isinstance(result, MealAnalysis)
    assert result.nutrition is None
    assert result.warnings == ()


def test_analyze_accepts_structured_ingredients() -> None:
    service = MealAnalysisService()
    command = MealAnalysisCommand(
        description="Breakfast bowl",
        ingredients=(MealIngredient(name="oats", quantity=80, unit="g"),),
    )

    result = service.analyze(command)

    assert result.nutrition is None
    assert result.warnings == ()


def test_factory_builds_a_service() -> None:
    assert isinstance(build_meal_analysis_service(), MealAnalysisService)
