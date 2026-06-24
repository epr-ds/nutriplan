"""Meal-analysis use case: described meal -> nutrition + alignment + warnings.

This is the application layer for ``POST /ai/analyze-meal``. AIA-301 shipped the transport seam;
AIA-302 fills it: a :class:`MealAnalysisService` assembles a localized prompt, asks the model for a
schema-constrained :class:`NutritionEstimateDraft`, normalizes it onto :class:`AnalyzedNutrition`,
scores it against a balanced-meal reference (reusing AIA-106) into a :class:`MealAlignment`, and
flags low-confidence estimates as warnings -- returning a :class:`MealAnalysis` the API projects.
"""

from app.analysis.alignment import MealAligner, MealReference
from app.analysis.assembler import (
    MealAnalysisPromptAssembler,
    build_meal_analysis_prompt_assembler,
)
from app.analysis.commands import MealAnalysisCommand, MealIngredient
from app.analysis.draft import NutritionEstimateDraft
from app.analysis.result import AnalyzedNutrition, MealAlignment, MealAnalysis
from app.analysis.service import MealAnalysisService, build_meal_analysis_service

__all__ = [
    "AnalyzedNutrition",
    "MealAligner",
    "MealAlignment",
    "MealAnalysis",
    "MealAnalysisCommand",
    "MealAnalysisPromptAssembler",
    "MealAnalysisService",
    "MealIngredient",
    "MealReference",
    "NutritionEstimateDraft",
    "build_meal_analysis_prompt_assembler",
    "build_meal_analysis_service",
]
