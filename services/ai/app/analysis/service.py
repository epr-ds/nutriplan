"""The meal-analysis use case (AIA-301): description (+ ingredients) -> nutrition + warnings.

This is the application service behind ``POST /ai/analyze-meal``. AIA-301 establishes the transport
seam: it accepts a :class:`MealAnalysisCommand` and returns a :class:`MealAnalysis`. The actual
estimation -- prompting the model, normalizing nutrients, and raising warnings -- arrives in AIA-302
behind this same interface, so the route and its wiring do not change when it lands.
"""

from __future__ import annotations

from app.analysis.commands import MealAnalysisCommand
from app.analysis.result import MealAnalysis


class MealAnalysisService:
    """Analyze a described meal's nutrition (AIA-302 fills in estimation behind this seam)."""

    def analyze(self, command: MealAnalysisCommand) -> MealAnalysis:
        """Return the analysis for ``command``; empty until estimation lands in AIA-302."""
        return MealAnalysis()


def build_meal_analysis_service() -> MealAnalysisService:
    """Wire the analysis service from configuration (no collaborators yet; AIA-302 adds them)."""
    return MealAnalysisService()
