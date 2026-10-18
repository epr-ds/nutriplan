"""Nutrition metadata API router (DPL-305)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentPrincipal
from app.api.schemas import NutritionDisclaimerResponse
from app.domain.nutrition_disclaimer import default_nutrition_disclaimer

router = APIRouter(prefix="/nutrition", tags=["Nutrition"])


@router.get(
    "/disclaimer",
    response_model=NutritionDisclaimerResponse,
    summary="Nutrition sources + medical disclaimer",
)
def get_nutrition_disclaimer(principal: CurrentPrincipal) -> NutritionDisclaimerResponse:
    """Return the catalog-wide nutrition source provenance + disclaimer (DPL-305).

    The metadata is static and catalog-wide: it lists the verified data sources the nutrition
    values are traceable to (with a per-nutrient field→source map) and the disclaimer the UI must
    surface. Requires authentication like the other catalog reads.
    """
    return NutritionDisclaimerResponse.from_domain(default_nutrition_disclaimer())
