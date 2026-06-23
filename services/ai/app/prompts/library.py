"""The prompts the AI service actually ships, versioned and localized (AIA-103).

This is the seed catalog the `/ai/*` endpoints build on from AIA-201. Each prompt is
defined once per supported locale with a shared ``version`` string; bump the version
whenever the wording changes so telemetry can tell completions from different revisions
apart. Versions use a date stamp -- monotonic, human-readable, and merge-friendly.
"""

from __future__ import annotations

from app.prompts.catalog import InMemoryPromptCatalog
from app.prompts.renderer import PromptRenderer
from app.prompts.telemetry import LoggingPromptTelemetry, PromptTelemetry
from app.prompts.template import PromptTemplate
from app.prompts.types import Locale

MEAL_RECOMMENDATION_ID = "meal_recommendation"
_MEAL_RECOMMENDATION_VERSION = "2026-06-01"

_MEAL_RECOMMENDATION_EN = PromptTemplate(
    id=MEAL_RECOMMENDATION_ID,
    version=_MEAL_RECOMMENDATION_VERSION,
    locale=Locale.EN,
    system=(
        "You are NutriPlan's registered-dietitian assistant. Recommend meals that fit "
        "the user's goal, dietary pattern, and energy target. Never suggest an "
        "ingredient the user is allergic to. Reply in English."
    ),
    user=(
        "Goal: $goal\n"
        "Dietary pattern: $diet\n"
        "Allergies: $allergies\n"
        "Daily energy target: $calories kcal\n\n"
        "Suggest $count meal ideas that respect the constraints above."
    ),
)

_MEAL_RECOMMENDATION_ES = PromptTemplate(
    id=MEAL_RECOMMENDATION_ID,
    version=_MEAL_RECOMMENDATION_VERSION,
    locale=Locale.ES,
    system=(
        "Eres el asistente dietista-nutricionista de NutriPlan. Recomienda comidas que "
        "se ajusten al objetivo, el patrón alimentario y el objetivo energético del "
        "usuario. Nunca sugieras un ingrediente al que el usuario sea alérgico. "
        "Responde en español."
    ),
    user=(
        "Objetivo: $goal\n"
        "Patrón alimentario: $diet\n"
        "Alergias: $allergies\n"
        "Objetivo de energía diaria: $calories kcal\n\n"
        "Sugiere $count ideas de comidas que respeten las restricciones anteriores."
    ),
)

DEFAULT_TEMPLATES: tuple[PromptTemplate, ...] = (
    _MEAL_RECOMMENDATION_EN,
    _MEAL_RECOMMENDATION_ES,
)


def build_default_catalog() -> InMemoryPromptCatalog:
    """Build a catalog pre-loaded with every shipped template."""
    return InMemoryPromptCatalog(DEFAULT_TEMPLATES)


def build_default_renderer(*, telemetry: PromptTelemetry | None = None) -> PromptRenderer:
    """Build a renderer over the shipped catalog, logging prompt versions by default."""
    return PromptRenderer(
        build_default_catalog(),
        telemetry=telemetry if telemetry is not None else LoggingPromptTelemetry(),
    )
