"""Assemble the localized analyze-meal prompt from a command (AIA-302).

Mirrors the recommendation assembler: it maps a :class:`MealAnalysisCommand` onto the
``analyze_meal`` template and a complete set of rendered variables, then delegates to the injected
:class:`~app.prompts.renderer.PromptRenderer` so prompt versioning, localization, and telemetry stay
in one place. Structured ingredients are rendered as a readable list -- with their amount and any
nutrition hints -- so the model can sharpen its estimate; an absent list becomes a neutral filler.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.analysis.commands import MealAnalysisCommand, MealIngredient
from app.prompts.library import ANALYZE_MEAL_ID, build_default_renderer
from app.prompts.renderer import PromptRenderer
from app.prompts.telemetry import PromptTelemetry
from app.prompts.types import Locale, RenderedPrompt

_DEFAULT_LOCALE = Locale.default()


@dataclass(frozen=True, slots=True)
class _LocaleText:
    """Locale-specific fillers and nutrient-hint labels injected into the prompt."""

    no_description: str
    none: str
    calories: str
    protein: str
    carbs: str
    fat: str
    sugar: str


_TEXT: Mapping[Locale, _LocaleText] = {
    Locale.EN: _LocaleText(
        no_description="no description provided",
        none="none provided",
        calories="kcal",
        protein="g protein",
        carbs="g carbs",
        fat="g fat",
        sugar="g sugar",
    ),
    Locale.ES: _LocaleText(
        no_description="sin descripción",
        none="ninguno",
        calories="kcal",
        protein="g de proteína",
        carbs="g de carbohidratos",
        fat="g de grasa",
        sugar="g de azúcar",
    ),
}


class MealAnalysisPromptAssembler:
    """Render the analyze-meal prompt for a command, in the requested locale."""

    def __init__(self, renderer: PromptRenderer) -> None:
        self._renderer = renderer

    def assemble(
        self,
        command: MealAnalysisCommand,
        *,
        locale: Locale | str = _DEFAULT_LOCALE,
    ) -> RenderedPrompt:
        """Render the analyze-meal template with the command's description and ingredients."""
        resolved = Locale.parse(locale, default=Locale.default())
        text = _TEXT[resolved]
        variables = {
            "description": command.description.strip() or text.no_description,
            "ingredients": _format_ingredients(command.ingredients, text),
        }
        return self._renderer.render(ANALYZE_MEAL_ID, locale=resolved, variables=variables)


def _format_ingredients(items: Iterable[MealIngredient], text: _LocaleText) -> str:
    rendered = "; ".join(_format_ingredient(item, text) for item in items)
    return rendered or text.none


def _format_ingredient(item: MealIngredient, text: _LocaleText) -> str:
    detail = ", ".join(_ingredient_details(item, text))
    return f"{item.name} ({detail})" if detail else item.name


def _ingredient_details(item: MealIngredient, text: _LocaleText) -> list[str]:
    parts: list[str] = []
    amount = _amount(item)
    if amount:
        parts.append(amount)
    for value, label in (
        (item.calories, text.calories),
        (item.protein, text.protein),
        (item.carbs, text.carbs),
        (item.fat, text.fat),
        (item.sugar, text.sugar),
    ):
        if value is not None:
            parts.append(f"{value:g} {label}")
    return parts


def _amount(item: MealIngredient) -> str:
    if item.quantity is None and not item.unit:
        return ""
    quantity = f"{item.quantity:g}" if item.quantity is not None else ""
    return " ".join(part for part in (quantity, item.unit or "") if part)


def build_meal_analysis_prompt_assembler(
    *, telemetry: PromptTelemetry | None = None
) -> MealAnalysisPromptAssembler:
    """Build an assembler over the shipped prompt catalog (logging versions by default)."""
    return MealAnalysisPromptAssembler(build_default_renderer(telemetry=telemetry))
