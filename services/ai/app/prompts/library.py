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


# --- Context-aware recommendation prompts (AIA-202) ---------------------------------------------
# Three contexts share one dietitian persona and one dietary-profile block, differing only in how
# the task is framed. The assembler always supplies every variable below (filling absent profile
# fields with neutral, localized text), so each template renders cleanly.

RECOMMEND_MEAL_PLAN_ID = "recommend_meal_plan"
RECOMMEND_SINGLE_MEAL_ID = "recommend_single_meal"
RECOMMEND_INGREDIENT_BASED_ID = "recommend_ingredient_based"
_RECOMMENDATION_VERSION = "2026-06-23"

_EN_PERSONA = (
    "You are NutriPlan's registered-dietitian assistant. Recommend meals that fit the user's "
    "dietary pattern, preferences, and energy needs. Never suggest an ingredient the user is "
    "allergic to or has excluded. Reply in English."
)
_ES_PERSONA = (
    "Eres el asistente dietista-nutricionista de NutriPlan. Recomienda comidas que se ajusten al "
    "patrón alimentario, las preferencias y las necesidades energéticas del usuario. Nunca "
    "sugieras un ingrediente al que el usuario sea alérgico o que haya excluido. Responde en "
    "español."
)

_EN_PROFILE = (
    "Dietary pattern: $diet\n"
    "Allergies (never include): $allergies\n"
    "Excluded ingredients: $excluded\n"
    "Preferred cuisines: $cuisines\n"
    "Energy target: $calories\n"
    "Macro targets: $macros\n"
    "Avoid repeating: $previous\n"
    "Additional constraints: $constraints"
)
_ES_PROFILE = (
    "Patrón alimentario: $diet\n"
    "Alergias (nunca incluir): $allergies\n"
    "Ingredientes excluidos: $excluded\n"
    "Cocinas preferidas: $cuisines\n"
    "Objetivo de energía: $calories\n"
    "Objetivos de macros: $macros\n"
    "Evita repetir: $previous\n"
    "Restricciones adicionales: $constraints"
)


def _recommendation_template(
    prompt_id: str, locale: Locale, *, persona: str, task: str
) -> PromptTemplate:
    profile = _EN_PROFILE if locale is Locale.EN else _ES_PROFILE
    return PromptTemplate(
        id=prompt_id,
        version=_RECOMMENDATION_VERSION,
        locale=locale,
        system=persona,
        user=f"{task}\n{profile}",
    )


_RECOMMEND_MEAL_PLAN_EN = _recommendation_template(
    RECOMMEND_MEAL_PLAN_ID,
    Locale.EN,
    persona=_EN_PERSONA,
    task=(
        "Recommend meals for a daily meal plan. Suggest $count meal ideas that together fit the "
        "day and respect every constraint below."
    ),
)
_RECOMMEND_MEAL_PLAN_ES = _recommendation_template(
    RECOMMEND_MEAL_PLAN_ID,
    Locale.ES,
    persona=_ES_PERSONA,
    task=(
        "Recomienda comidas para un plan diario. Sugiere $count ideas de comidas que en conjunto "
        "encajen en el día y respeten cada restricción siguiente."
    ),
)

_RECOMMEND_SINGLE_MEAL_EN = _recommendation_template(
    RECOMMEND_SINGLE_MEAL_ID,
    Locale.EN,
    persona=_EN_PERSONA,
    task=(
        "Recommend a single $meal_type. Suggest $count options that respect every constraint below."
    ),
)
_RECOMMEND_SINGLE_MEAL_ES = _recommendation_template(
    RECOMMEND_SINGLE_MEAL_ID,
    Locale.ES,
    persona=_ES_PERSONA,
    task=(
        "Recomienda una sola comida de tipo $meal_type. Sugiere $count opciones que respeten cada "
        "restricción siguiente."
    ),
)

_RECOMMEND_INGREDIENT_BASED_EN = _recommendation_template(
    RECOMMEND_INGREDIENT_BASED_ID,
    Locale.EN,
    persona=_EN_PERSONA,
    task=(
        "Recommend meals built mainly from these available ingredients: $ingredients.\n"
        "Meal: $meal_type. Prefer the available ingredients, keep extra additions minimal, and "
        "suggest $count options that respect every constraint below."
    ),
)
_RECOMMEND_INGREDIENT_BASED_ES = _recommendation_template(
    RECOMMEND_INGREDIENT_BASED_ID,
    Locale.ES,
    persona=_ES_PERSONA,
    task=(
        "Recomienda comidas elaboradas principalmente con estos ingredientes disponibles: "
        "$ingredients.\nComida: $meal_type. Prioriza los ingredientes disponibles, añade lo mínimo "
        "extra y sugiere $count opciones que respeten cada restricción siguiente."
    ),
)

DEFAULT_TEMPLATES = (
    *DEFAULT_TEMPLATES,
    _RECOMMEND_MEAL_PLAN_EN,
    _RECOMMEND_MEAL_PLAN_ES,
    _RECOMMEND_SINGLE_MEAL_EN,
    _RECOMMEND_SINGLE_MEAL_ES,
    _RECOMMEND_INGREDIENT_BASED_EN,
    _RECOMMEND_INGREDIENT_BASED_ES,
)


# --- Meal-analysis prompt (AIA-302) -------------------------------------------------------------
# Estimate a described meal's nutrition. The assembler always supplies $description and a rendered
# $ingredients list (filling an absent list with a neutral filler), so the template renders cleanly.

ANALYZE_MEAL_ID = "analyze_meal"
_ANALYZE_MEAL_VERSION = "2026-06-23"

_ANALYZE_MEAL_EN = PromptTemplate(
    id=ANALYZE_MEAL_ID,
    version=_ANALYZE_MEAL_VERSION,
    locale=Locale.EN,
    system=(
        "You are NutriPlan's registered-dietitian assistant. Estimate the "
        "nutrition of the meal the user describes, using any structured "
        "ingredients to sharpen the estimate. Report whole-meal totals: "
        "calories in kcal and protein, carbohydrates, fat, and sugar in grams, "
        "plus a confidence between 0 and 1. Do not give medical advice or "
        "health claims. Reply in English."
    ),
    user=(
        "Meal description: $description\n"
        "Ingredients: $ingredients\n"
        "Estimate the whole meal's calories and macronutrients, and rate your "
        "confidence from 0 to 1."
    ),
)

_ANALYZE_MEAL_ES = PromptTemplate(
    id=ANALYZE_MEAL_ID,
    version=_ANALYZE_MEAL_VERSION,
    locale=Locale.ES,
    system=(
        "Eres el asistente dietista-nutricionista de NutriPlan. Estima la "
        "nutrición de la comida que describe el usuario, usando los "
        "ingredientes estructurados para afinar la estimación. Indica los "
        "totales de la comida completa: calorías en kcal y proteínas, "
        "carbohidratos, grasas y azúcar en gramos, además de una confianza "
        "entre 0 y 1. No des consejo médico ni afirmaciones de salud. "
        "Responde en español."
    ),
    user=(
        "Descripción de la comida: $description\n"
        "Ingredientes: $ingredients\n"
        "Estima las calorías y los macronutrientes de la comida completa, y "
        "valora tu confianza de 0 a 1."
    ),
)

DEFAULT_TEMPLATES = (
    *DEFAULT_TEMPLATES,
    _ANALYZE_MEAL_EN,
    _ANALYZE_MEAL_ES,
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
