"""Assembles a localized, preference-aware recommendation prompt (AIA-202).

The assembler maps a :class:`~app.recommendations.commands.RecommendationCommand` onto the right
context template and a complete set of rendered variables, then delegates to the injected
:class:`~app.prompts.renderer.PromptRenderer` so prompt versioning, localization, and telemetry stay
in one place. Optional profile fields are formatted with neutral, locale-appropriate fillers, so the
template always renders -- a missing allergy list becomes "none"/"ninguna", never a blank line or a
leftover ``$placeholder``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.prompts.library import (
    RECOMMEND_INGREDIENT_BASED_ID,
    RECOMMEND_MEAL_PLAN_ID,
    RECOMMEND_SINGLE_MEAL_ID,
    build_default_renderer,
)
from app.prompts.renderer import PromptRenderer
from app.prompts.telemetry import PromptTelemetry
from app.prompts.types import Locale, RenderedPrompt
from app.recommendations.commands import (
    MacroTargets,
    RecommendationCommand,
    RecommendationContext,
)

_PROMPT_IDS: Mapping[RecommendationContext, str] = {
    RecommendationContext.MEAL_PLAN: RECOMMEND_MEAL_PLAN_ID,
    RecommendationContext.SINGLE_MEAL: RECOMMEND_SINGLE_MEAL_ID,
    RecommendationContext.INGREDIENT_BASED: RECOMMEND_INGREDIENT_BASED_ID,
}

_DEFAULT_LOCALE = Locale.default()


@dataclass(frozen=True, slots=True)
class _LocaleText:
    """Locale-specific filler words and macro labels injected for absent fields."""

    none: str
    no_diet: str
    no_cuisine: str
    no_calories: str
    no_macros: str
    any_ingredients: str
    any_meal: str
    protein: str
    carbs: str
    fat: str
    sugar: str


_TEXT: Mapping[Locale, _LocaleText] = {
    Locale.EN: _LocaleText(
        none="none",
        no_diet="no specific dietary pattern",
        no_cuisine="no preference",
        no_calories="no specific target",
        no_macros="no specific targets",
        any_ingredients="any available",
        any_meal="any meal",
        protein="protein",
        carbs="carbs",
        fat="fat",
        sugar="sugar",
    ),
    Locale.ES: _LocaleText(
        none="ninguna",
        no_diet="sin patrón alimentario específico",
        no_cuisine="sin preferencia",
        no_calories="sin objetivo específico",
        no_macros="sin objetivos específicos",
        any_ingredients="cualquiera disponible",
        any_meal="cualquier comida",
        protein="proteínas",
        carbs="carbohidratos",
        fat="grasas",
        sugar="azúcar",
    ),
}


class RecommendationPromptAssembler:
    """Render the recommendation prompt for a command, in the requested locale."""

    def __init__(self, renderer: PromptRenderer) -> None:
        self._renderer = renderer

    def assemble(
        self,
        command: RecommendationCommand,
        *,
        locale: Locale | str = _DEFAULT_LOCALE,
    ) -> RenderedPrompt:
        """Resolve the context template and render it with the command's profile injected."""
        resolved = Locale.parse(locale, default=Locale.default())
        prompt_id = _PROMPT_IDS[command.context]
        variables = self._variables(command, _TEXT[resolved])
        return self._renderer.render(prompt_id, locale=resolved, variables=variables)

    def _variables(self, command: RecommendationCommand, text: _LocaleText) -> dict[str, object]:
        calories = command.effective_calories()
        return {
            "diet": command.diet_type or text.no_diet,
            "allergies": _join(command.allergies, text.none),
            "excluded": _join(command.excluded_ingredients, text.none),
            "cuisines": _join(command.cuisine_preferences, text.no_cuisine),
            "calories": f"{calories} kcal" if calories else text.no_calories,
            "macros": _format_macros(command.macro_targets, text),
            "ingredients": _join(command.available_ingredients, text.any_ingredients),
            "meal_type": str(command.meal_type) if command.meal_type else text.any_meal,
            "previous": _join(command.previous_meals, text.none),
            "constraints": _join(command.constraints, text.none),
            "count": command.count,
        }


def _join(items: Iterable[str], filler: str) -> str:
    joined = ", ".join(item for item in items if item)
    return joined or filler


def _format_macros(macros: MacroTargets | None, text: _LocaleText) -> str:
    if macros is None or macros.is_empty():
        return text.no_macros
    parts: list[str] = []
    for value, label in (
        (macros.protein_grams, text.protein),
        (macros.carbs_grams, text.carbs),
        (macros.fat_grams, text.fat),
        (macros.sugar_grams, text.sugar),
    ):
        if value is not None:
            parts.append(f"{label} {value} g")
    return ", ".join(parts) if parts else text.no_macros


def build_recommendation_prompt_assembler(
    *, telemetry: PromptTelemetry | None = None
) -> RecommendationPromptAssembler:
    """Build an assembler over the shipped prompt catalog (logging versions by default)."""
    return RecommendationPromptAssembler(build_default_renderer(telemetry=telemetry))
