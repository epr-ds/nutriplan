"""Build and localize the advisory warnings a meal analysis surfaces (AIA-303).

AIA-302 emitted a single low-confidence flag; this completes Epic E3 by adding two more advisory
categories -- nutrients that land well over/under a balanced meal, and common allergens the model
detected -- and localizing every warning es/en.

The split is deliberate. :func:`build_warnings` is pure and locale-independent: it turns the
low-confidence decision, the normalized nutrition, the meal reference, and the model's reported
allergens into :class:`MealWarning` *findings*. :func:`localize_all` then renders each finding from
a **fixed vocabulary**. Two properties fall out of that design:

* allergen findings are normalized to a canonical token, so the model's own prose is never echoed
  back to the user -- an unmappable token (which is where a stray health claim would hide) is simply
  dropped; and
* every rendered string is descriptive, never prescriptive -- there are no medical claims (the
  spirit of AIA-505), which a test pins across the whole vocabulary.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from app.analysis.alignment import MealReference
from app.analysis.result import AnalyzedNutrition
from app.prompts.types import Locale

# Nutrients we bound-check, in a fixed order so a meal's warnings are deterministic.
_BOUNDED_NUTRIENTS = ("calories", "protein", "carbs", "fat", "sugar")

# A nutrient is flagged when it lands far from the balanced-meal reference: at or above 1.5x is
# "high", at or below 0.5x is "low". The band between is treated as ordinary single-meal variation.
_OVER_RATIO = 1.5
_UNDER_RATIO = 0.5

# Sugar is only ever flagged high -- a low-sugar meal is not something to warn a user about.
_OVER_ONLY = frozenset({"sugar"})

# The canonical allergens we can localize, in the order their warnings should appear.
_ALLERGEN_ORDER = (
    "milk",
    "eggs",
    "peanuts",
    "tree_nuts",
    "soy",
    "wheat",
    "gluten",
    "fish",
    "shellfish",
    "sesame",
)

# Map the many ways a model might name an allergen onto a canonical token. Anything absent here is
# dropped rather than guessed at, which keeps unlocalizable model prose out of the warnings.
_ALLERGEN_SYNONYMS: Mapping[str, str] = {
    "milk": "milk",
    "dairy": "milk",
    "lactose": "milk",
    "egg": "eggs",
    "eggs": "eggs",
    "peanut": "peanuts",
    "peanuts": "peanuts",
    "ground nut": "peanuts",
    "ground nuts": "peanuts",
    "groundnut": "peanuts",
    "groundnuts": "peanuts",
    "tree nut": "tree_nuts",
    "tree nuts": "tree_nuts",
    "tree_nuts": "tree_nuts",
    "nut": "tree_nuts",
    "nuts": "tree_nuts",
    "almond": "tree_nuts",
    "almonds": "tree_nuts",
    "walnut": "tree_nuts",
    "walnuts": "tree_nuts",
    "cashew": "tree_nuts",
    "cashews": "tree_nuts",
    "hazelnut": "tree_nuts",
    "hazelnuts": "tree_nuts",
    "pecan": "tree_nuts",
    "pecans": "tree_nuts",
    "pistachio": "tree_nuts",
    "pistachios": "tree_nuts",
    "soy": "soy",
    "soya": "soy",
    "soja": "soy",
    "soybean": "soy",
    "soybeans": "soy",
    "wheat": "wheat",
    "gluten": "gluten",
    "fish": "fish",
    "shellfish": "shellfish",
    "crustacean": "shellfish",
    "crustaceans": "shellfish",
    "shrimp": "shellfish",
    "shrimps": "shellfish",
    "prawn": "shellfish",
    "prawns": "shellfish",
    "crab": "shellfish",
    "lobster": "shellfish",
    "mollusc": "shellfish",
    "molluscs": "shellfish",
    "mollusk": "shellfish",
    "mollusks": "shellfish",
    "clam": "shellfish",
    "clams": "shellfish",
    "oyster": "shellfish",
    "oysters": "shellfish",
    "mussel": "shellfish",
    "mussels": "shellfish",
    "sesame": "sesame",
    "tahini": "sesame",
}


class WarningKind(StrEnum):
    """The advisory categories a meal analysis can raise (AIA-303)."""

    LOW_CONFIDENCE = "low_confidence"
    OVER_TARGET = "over_target"
    UNDER_TARGET = "under_target"
    ALLERGEN = "allergen"


@dataclass(frozen=True, slots=True)
class MealWarning:
    """One locale-independent finding: a kind plus its subject.

    ``subject`` is the nutrient name for the bounds kinds, the canonical allergen token for
    :attr:`WarningKind.ALLERGEN`, and empty for :attr:`WarningKind.LOW_CONFIDENCE`.
    """

    kind: WarningKind
    subject: str = ""


def build_warnings(
    *,
    low_confidence: bool,
    nutrition: AnalyzedNutrition | None,
    reference: MealReference,
    allergens: Iterable[str],
) -> tuple[MealWarning, ...]:
    """Assemble every applicable finding, in a stable order: confidence, bounds, then allergens."""
    findings: list[MealWarning] = []
    if low_confidence:
        findings.append(MealWarning(WarningKind.LOW_CONFIDENCE))
    findings.extend(_bounds_findings(nutrition, reference))
    findings.extend(_allergen_findings(allergens))
    return tuple(findings)


def localize_all(warnings: Iterable[MealWarning], locale: Locale) -> tuple[str, ...]:
    """Render each finding into a localized, claim-free advisory string."""
    return tuple(_localize(warning, locale) for warning in warnings)


def _bounds_findings(
    nutrition: AnalyzedNutrition | None, reference: MealReference
) -> list[MealWarning]:
    if nutrition is None:
        return []
    findings: list[MealWarning] = []
    for name in _BOUNDED_NUTRIENTS:
        actual = getattr(nutrition, name)
        target = getattr(reference, name)
        if actual is None or target is None or target <= 0:
            continue
        ratio = actual / target
        if ratio >= _OVER_RATIO:
            findings.append(MealWarning(WarningKind.OVER_TARGET, name))
        elif ratio <= _UNDER_RATIO and name not in _OVER_ONLY:
            findings.append(MealWarning(WarningKind.UNDER_TARGET, name))
    return findings


def _allergen_findings(allergens: Iterable[str]) -> list[MealWarning]:
    seen: set[str] = set()
    for raw in allergens:
        canonical = _ALLERGEN_SYNONYMS.get(" ".join(raw.lower().split()))
        if canonical is not None:
            seen.add(canonical)
    return [MealWarning(WarningKind.ALLERGEN, name) for name in _ALLERGEN_ORDER if name in seen]


def _localize(warning: MealWarning, locale: Locale) -> str:
    if warning.kind is WarningKind.LOW_CONFIDENCE:
        return _LOW_CONFIDENCE[locale]
    if warning.kind is WarningKind.OVER_TARGET:
        return _OVER_TEMPLATE[locale].format(nutrient=_NUTRIENT_NAMES[locale][warning.subject])
    if warning.kind is WarningKind.UNDER_TARGET:
        return _UNDER_TEMPLATE[locale].format(nutrient=_NUTRIENT_NAMES[locale][warning.subject])
    return _ALLERGEN_TEMPLATE[locale].format(allergen=_ALLERGEN_NAMES[locale][warning.subject])


_LOW_CONFIDENCE: Mapping[Locale, str] = {
    Locale.EN: "This nutrition estimate has low confidence; the values are approximate.",
    Locale.ES: ("Esta estimación nutricional tiene baja confianza; los valores son aproximados."),
}

_OVER_TEMPLATE: Mapping[Locale, str] = {
    Locale.EN: "This meal is high in {nutrient} compared with a balanced meal.",
    Locale.ES: "Esta comida es alta en {nutrient} en comparación con una comida balanceada.",
}

_UNDER_TEMPLATE: Mapping[Locale, str] = {
    Locale.EN: "This meal is low in {nutrient} compared with a balanced meal.",
    Locale.ES: "Esta comida es baja en {nutrient} en comparación con una comida balanceada.",
}

_ALLERGEN_TEMPLATE: Mapping[Locale, str] = {
    Locale.EN: "Contains a common allergen: {allergen}.",
    Locale.ES: "Contiene un alérgeno común: {allergen}.",
}

_NUTRIENT_NAMES: Mapping[Locale, Mapping[str, str]] = {
    Locale.EN: {
        "calories": "calories",
        "protein": "protein",
        "carbs": "carbohydrates",
        "fat": "fat",
        "sugar": "sugar",
    },
    Locale.ES: {
        "calories": "calorías",
        "protein": "proteínas",
        "carbs": "carbohidratos",
        "fat": "grasa",
        "sugar": "azúcar",
    },
}

_ALLERGEN_NAMES: Mapping[Locale, Mapping[str, str]] = {
    Locale.EN: {
        "milk": "milk",
        "eggs": "eggs",
        "peanuts": "peanuts",
        "tree_nuts": "tree nuts",
        "soy": "soy",
        "wheat": "wheat",
        "gluten": "gluten",
        "fish": "fish",
        "shellfish": "shellfish",
        "sesame": "sesame",
    },
    Locale.ES: {
        "milk": "lácteos",
        "eggs": "huevo",
        "peanuts": "cacahuetes",
        "tree_nuts": "frutos secos",
        "soy": "soja",
        "wheat": "trigo",
        "gluten": "gluten",
        "fish": "pescado",
        "shellfish": "mariscos",
        "sesame": "sésamo",
    },
}
