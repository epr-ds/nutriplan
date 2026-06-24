"""The schema the model must fill when estimating a meal's nutrition (AIA-302).

This Pydantic model is the structured-output contract for the analyze-meal call: the AIA-104 loop
turns ``NutritionEstimateDraft`` into the provider's response-format constraint *and* validates the
reply against it. Every field is optional -- the model may genuinely not know a nutrient, and a
fully empty draft is the degraded "could not estimate" result the fallback returns. ``confidence``
is the model's own 0-1 self-rating; the estimator clamps and thresholds it to flag shaky estimates.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class NutritionEstimateDraft(BaseModel):
    """Whole-meal nutrition the model estimates, plus its self-reported confidence."""

    calories: int | None = None
    protein: int | None = None
    carbs: int | None = None
    fat: int | None = None
    sugar: int | None = None
    confidence: float | None = Field(
        default=None,
        description="The model's own confidence in this estimate, from 0 (a guess) to 1 (certain).",
    )
