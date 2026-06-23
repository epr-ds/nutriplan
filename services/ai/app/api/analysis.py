"""``POST /ai/analyze-meal`` — nutritional analysis of a described meal.

The transport edge (Bearer auth, request validation, the ``NutritionalAnalysisResponse`` envelope)
arrives in AIA-301. The route maps its validated request onto a
:class:`~app.analysis.commands.MealAnalysisCommand`, delegates to the injected analysis service, and
projects the result onto the wire shape. The estimation behind the service lands in AIA-302 without
changing this edge.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.analysis.commands import MealAnalysisCommand, MealIngredient
from app.api.deps import BearerToken, MealAnalysisServiceDep
from app.api.schemas import AnalyzeMealRequest, NutritionalAnalysisResponse

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/analyze-meal", response_model=NutritionalAnalysisResponse)
def analyze_meal(
    request: AnalyzeMealRequest,
    _token: BearerToken,
    service: MealAnalysisServiceDep,
) -> NutritionalAnalysisResponse:
    """Analyze the described meal's nutrition for the validated request."""
    analysis = service.analyze(_to_command(request))
    return NutritionalAnalysisResponse.from_analysis(analysis)


def _to_command(request: AnalyzeMealRequest) -> MealAnalysisCommand:
    """Translate the HTTP request into the application command the service consumes."""
    return MealAnalysisCommand(
        description=request.description,
        ingredients=tuple(
            MealIngredient(
                name=item.name,
                quantity=item.quantity,
                unit=item.unit,
                calories=item.calories,
                protein=item.protein,
                carbs=item.carbs,
                fat=item.fat,
                sugar=item.sugar,
            )
            for item in request.ingredients
        ),
    )
