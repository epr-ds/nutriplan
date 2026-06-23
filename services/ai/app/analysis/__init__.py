"""Meal-analysis use case: description (+ ingredients) -> nutrition + warnings.

This is the application layer for ``POST /ai/analyze-meal``. AIA-301 ships the transport seam: a
:class:`MealAnalysisCommand` captures the validated request, and a :class:`MealAnalysisService`
returns a :class:`MealAnalysis` (nutrition plus advisory warnings). The estimation itself lands in
AIA-302 behind the same service interface, so the API wiring is stable across that change.
"""

from app.analysis.commands import MealAnalysisCommand, MealIngredient
from app.analysis.result import AnalyzedNutrition, MealAnalysis
from app.analysis.service import MealAnalysisService, build_meal_analysis_service

__all__ = [
    "AnalyzedNutrition",
    "MealAnalysis",
    "MealAnalysisCommand",
    "MealAnalysisService",
    "MealIngredient",
    "build_meal_analysis_service",
]
