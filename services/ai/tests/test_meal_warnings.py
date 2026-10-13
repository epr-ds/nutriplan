"""Unit tests for the meal-analysis warning builder + localizer (AIA-303).

The builder is pure: it turns the low-confidence flag, the normalized nutrition, the meal
reference, and the model's reported allergens into locale-independent
:class:`~app.analysis.warnings.MealWarning` findings; the localizer renders them into es/en
strings drawn from a fixed vocabulary (so model prose never reaches the user and no medical
claim can slip in).
"""

from __future__ import annotations

from app.analysis.alignment import MealReference
from app.analysis.result import AnalyzedNutrition
from app.analysis.warnings import (
    MealWarning,
    WarningKind,
    build_warnings,
    localize_all,
)
from app.prompts.types import Locale

_REFERENCE = MealReference(calories=650, protein=30, carbs=80, fat=22, sugar=15)

# Phrases that would turn an informational warning into a medical claim. None may appear.
_MEDICAL_TERMS = (
    "doctor",
    "medical",
    "disease",
    "diabetes",
    "cholesterol",
    "diagnos",
    "cure",
    "treat",
    "prescri",
    "medico",
    "médico",
    "enfermedad",
    "colesterol",
    "diagnost",
    "cura",
    "receta",
    "consulta",
)


def _kinds(warnings: tuple[MealWarning, ...]) -> list[WarningKind]:
    return [warning.kind for warning in warnings]


def test_low_confidence_finding_is_first() -> None:
    warnings = build_warnings(
        low_confidence=True,
        nutrition=AnalyzedNutrition(calories=650, protein=30, carbs=80, fat=22, sugar=15),
        reference=_REFERENCE,
        allergens=(),
    )

    assert warnings[0] == MealWarning(WarningKind.LOW_CONFIDENCE)


def test_balanced_meal_raises_no_bounds_warning() -> None:
    warnings = build_warnings(
        low_confidence=False,
        nutrition=AnalyzedNutrition(calories=650, protein=30, carbs=80, fat=22, sugar=15),
        reference=_REFERENCE,
        allergens=(),
    )

    assert warnings == ()


def test_over_target_nutrient_is_flagged() -> None:
    # 1300 kcal is 2x the 650 reference -> over target.
    warnings = build_warnings(
        low_confidence=False,
        nutrition=AnalyzedNutrition(calories=1300, protein=30, carbs=80, fat=22, sugar=15),
        reference=_REFERENCE,
        allergens=(),
    )

    assert MealWarning(WarningKind.OVER_TARGET, "calories") in warnings


def test_under_target_nutrient_is_flagged() -> None:
    # 10 g protein is a third of the 30 g reference -> under target.
    warnings = build_warnings(
        low_confidence=False,
        nutrition=AnalyzedNutrition(calories=650, protein=10, carbs=80, fat=22, sugar=15),
        reference=_REFERENCE,
        allergens=(),
    )

    assert MealWarning(WarningKind.UNDER_TARGET, "protein") in warnings


def test_sugar_is_flagged_high_but_never_low() -> None:
    high = build_warnings(
        low_confidence=False,
        nutrition=AnalyzedNutrition(calories=650, protein=30, carbs=80, fat=22, sugar=40),
        reference=_REFERENCE,
        allergens=(),
    )
    low = build_warnings(
        low_confidence=False,
        nutrition=AnalyzedNutrition(calories=650, protein=30, carbs=80, fat=22, sugar=2),
        reference=_REFERENCE,
        allergens=(),
    )

    assert MealWarning(WarningKind.OVER_TARGET, "sugar") in high
    assert all(w.subject != "sugar" for w in low)


def test_unknown_nutrient_is_not_bounds_checked() -> None:
    warnings = build_warnings(
        low_confidence=False,
        nutrition=AnalyzedNutrition(calories=None, protein=10, carbs=None, fat=None, sugar=None),
        reference=_REFERENCE,
        allergens=(),
    )

    assert _kinds(warnings) == [WarningKind.UNDER_TARGET]
    assert all(w.subject != "calories" for w in warnings)


def test_no_bounds_when_nutrition_is_unknown() -> None:
    warnings = build_warnings(
        low_confidence=True,
        nutrition=None,
        reference=_REFERENCE,
        allergens=("peanuts",),
    )

    assert _kinds(warnings) == [WarningKind.LOW_CONFIDENCE, WarningKind.ALLERGEN]


def test_canonical_allergen_is_flagged() -> None:
    warnings = build_warnings(
        low_confidence=False,
        nutrition=None,
        reference=_REFERENCE,
        allergens=("peanuts",),
    )

    assert warnings == (MealWarning(WarningKind.ALLERGEN, "peanuts"),)


def test_allergen_synonyms_are_normalized() -> None:
    warnings = build_warnings(
        low_confidence=False,
        nutrition=None,
        reference=_REFERENCE,
        allergens=("Dairy", "soya", "ground nuts", "  EGG  "),
    )

    subjects = {w.subject for w in warnings if w.kind is WarningKind.ALLERGEN}
    assert subjects == {"milk", "soy", "peanuts", "eggs"}


def test_unknown_allergens_are_dropped() -> None:
    # An unmappable token (here, model prose) cannot be safely localized, so it is dropped
    # rather than echoed -- this is what keeps medical claims out of the warnings.
    warnings = build_warnings(
        low_confidence=False,
        nutrition=None,
        reference=_REFERENCE,
        allergens=("kale", "may cause heart disease", "milk"),
    )

    assert warnings == (MealWarning(WarningKind.ALLERGEN, "milk"),)


def test_allergens_are_deduplicated() -> None:
    warnings = build_warnings(
        low_confidence=False,
        nutrition=None,
        reference=_REFERENCE,
        allergens=("milk", "dairy", "MILK"),
    )

    assert warnings == (MealWarning(WarningKind.ALLERGEN, "milk"),)


def test_findings_are_ordered_confidence_then_bounds_then_allergens() -> None:
    warnings = build_warnings(
        low_confidence=True,
        nutrition=AnalyzedNutrition(calories=1300, protein=10, carbs=80, fat=22, sugar=15),
        reference=_REFERENCE,
        allergens=("peanuts",),
    )

    assert _kinds(warnings) == [
        WarningKind.LOW_CONFIDENCE,
        WarningKind.OVER_TARGET,
        WarningKind.UNDER_TARGET,
        WarningKind.ALLERGEN,
    ]


def test_localizes_every_finding_in_english() -> None:
    warnings = (
        MealWarning(WarningKind.LOW_CONFIDENCE),
        MealWarning(WarningKind.OVER_TARGET, "calories"),
        MealWarning(WarningKind.UNDER_TARGET, "protein"),
        MealWarning(WarningKind.ALLERGEN, "peanuts"),
    )

    text = localize_all(warnings, Locale.EN)

    assert any("confidence" in line.lower() for line in text)
    assert any("high" in line.lower() and "calories" in line.lower() for line in text)
    assert any("low" in line.lower() and "protein" in line.lower() for line in text)
    assert any("peanuts" in line.lower() for line in text)


def test_localizes_every_finding_in_spanish() -> None:
    warnings = (
        MealWarning(WarningKind.LOW_CONFIDENCE),
        MealWarning(WarningKind.OVER_TARGET, "calories"),
        MealWarning(WarningKind.UNDER_TARGET, "protein"),
        MealWarning(WarningKind.ALLERGEN, "peanuts"),
    )

    text = localize_all(warnings, Locale.ES)

    assert any("confianza" in line.lower() for line in text)
    assert any("alta" in line.lower() and "calor" in line.lower() for line in text)
    assert any("baja" in line.lower() and "prote" in line.lower() for line in text)
    assert any("cacahuete" in line.lower() for line in text)


def test_localized_warnings_make_no_medical_claims() -> None:
    # Render the full vocabulary in both locales and assert none of it reads as medical advice.
    every_finding = (
        MealWarning(WarningKind.LOW_CONFIDENCE),
        *(
            MealWarning(WarningKind.OVER_TARGET, n)
            for n in ("calories", "protein", "carbs", "fat", "sugar")
        ),
        *(
            MealWarning(WarningKind.UNDER_TARGET, n)
            for n in ("calories", "protein", "carbs", "fat")
        ),
        *(
            MealWarning(WarningKind.ALLERGEN, a)
            for a in (
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
        ),
    )

    for locale in (Locale.EN, Locale.ES):
        for line in localize_all(every_finding, locale):
            lowered = line.lower()
            assert not any(term in lowered for term in _MEDICAL_TERMS), line
