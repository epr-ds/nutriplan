"""``POST /ai/recommendations`` — AI recipe recommendations.

The transport edge (Bearer auth, request validation, the ``AIRecommendationResponse`` envelope)
arrived in AIA-201; AIA-203 wired the recommendation service behind it so the response carries real,
usable recipes; AIA-204 adds the model's ``reasoning`` and a deterministic ``nutritionalAlignment``
(scored via AIA-106); AIA-505 attaches the medical ``disclaimer``. The route maps its validated
request onto a :class:`~app.recommendations.commands.RecommendationCommand`, delegates to the
injected service, and projects the result onto the wire shape.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import BearerToken, RecommendationServiceDep
from app.api.schemas import (
    AIRecommendationRequest,
    AIRecommendationResponse,
    DietaryPreferencesSchema,
    NutritionalAlignmentResponse,
    RecipeResponse,
)
from app.prompts.types import Locale
from app.recommendations.commands import (
    MacroTargets,
    MealType,
    RecommendationCommand,
    RecommendationContext,
)

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/recommendations", response_model=AIRecommendationResponse)
def get_recommendations(
    request: AIRecommendationRequest,
    _token: BearerToken,
    service: RecommendationServiceDep,
) -> AIRecommendationResponse:
    """Recommend recipes for the validated request, localized to the requested language."""
    command = _to_command(request)
    locale = Locale.parse(request.language.value, default=Locale.default())
    result = service.recommend(command, locale=locale)
    alignment = result.alignment
    return AIRecommendationResponse(
        recommendations=[RecipeResponse.from_recommended(recipe) for recipe in result.recipes],
        reasoning=result.reasoning,
        nutritional_alignment=(
            NutritionalAlignmentResponse.from_alignment(alignment)
            if alignment is not None
            else None
        ),
        disclaimer=result.disclaimer,
    )


def _to_command(request: AIRecommendationRequest) -> RecommendationCommand:
    """Translate the HTTP request into the application command the service consumes."""
    prefs = request.dietary_preferences or DietaryPreferencesSchema()
    return RecommendationCommand(
        context=RecommendationContext(request.context.value),
        diet_type=prefs.diet_type.value if prefs.diet_type is not None else None,
        allergies=tuple(prefs.allergies),
        excluded_ingredients=tuple(prefs.excluded_ingredients),
        cuisine_preferences=tuple(prefs.cuisine_preferences),
        daily_calorie_target=prefs.daily_calorie_target,
        macro_targets=_to_macros(prefs),
        available_ingredients=tuple(request.available_ingredients),
        meal_type=MealType(request.meal_type.value) if request.meal_type is not None else None,
        calorie_target=request.calorie_target,
        previous_meals=tuple(request.previous_meals),
        constraints=tuple(request.constraints),
    )


def _to_macros(prefs: DietaryPreferencesSchema) -> MacroTargets | None:
    targets = prefs.macro_targets
    if targets is None:
        return None
    return MacroTargets(
        protein_grams=targets.protein_grams,
        carbs_grams=targets.carbs_grams,
        fat_grams=targets.fat_grams,
        sugar_grams=targets.sugar_grams,
    )
