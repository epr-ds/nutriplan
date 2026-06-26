"""Tests for the response post-processor (AIA-505).

Sanitizing input (AIA-504) and screening unsafe output keep the AI safe; this guard keeps it
*compliant*. :class:`ResponsePostProcessor` (1) attaches a localized medical disclaimer to every
response and (2) removes any sentence of generated free-text that reads like a health claim --
curing/treating/preventing a condition, a diagnosis, a clinical-authority boast, or a physiological
-effect claim -- recording each through a telemetry port. Ordinary food language is returned
verbatim. Everything here is pure -- no LLM, no I/O.
"""

from __future__ import annotations

import logging

import pytest

from app.guardrails.compliance import (
    InMemoryMedicalClaimTelemetry,
    LoggingMedicalClaimTelemetry,
    MedicalClaimCategory,
    MedicalClaimEvent,
    ResponsePostProcessor,
)
from app.prompts.types import Locale


def _processor(telemetry: InMemoryMedicalClaimTelemetry | None = None) -> ResponsePostProcessor:
    return ResponsePostProcessor(telemetry or InMemoryMedicalClaimTelemetry())


# --- Disclaimer (AC1) ----------------------------------------------------------------------------


def test_disclaimer_english() -> None:
    text = _processor().disclaimer(Locale.EN)

    assert "AI-generated" in text
    assert "not medical advice" in text
    assert "healthcare professional" in text


def test_disclaimer_spanish() -> None:
    text = _processor().disclaimer(Locale.ES)

    assert "IA" in text
    assert "consejo médico" in text
    assert "profesional de la salud" in text


def test_disclaimer_accepts_locale_string() -> None:
    processor = _processor()

    assert processor.disclaimer("es-MX") == processor.disclaimer(Locale.ES)
    assert processor.disclaimer("en_US") == processor.disclaimer(Locale.EN)


def test_disclaimer_defaults_to_english() -> None:
    processor = _processor()

    assert processor.disclaimer() == processor.disclaimer(Locale.EN)


def test_unknown_locale_falls_back_to_default_disclaimer() -> None:
    processor = _processor()

    assert processor.disclaimer("fr") == processor.disclaimer(Locale.default())


# --- Benign text is verbatim (no false positives) ------------------------------------------------


def test_benign_recipe_text_is_returned_verbatim() -> None:
    telemetry = InMemoryMedicalClaimTelemetry()
    text = "Oatmeal is a healthy breakfast. It is high in protein and low in sugar."

    assert _processor(telemetry).scrub(text) == text
    assert telemetry.count == 0


def test_strong_food_words_are_not_claims() -> None:
    telemetry = InMemoryMedicalClaimTelemetry()
    text = "A sweet treat for healthy eaters. This wholesome bowl helps you feel great."

    assert _processor(telemetry).scrub(text) == text
    assert telemetry.count == 0


def test_reducing_calories_is_not_a_health_claim() -> None:
    telemetry = InMemoryMedicalClaimTelemetry()
    text = "This light dinner reduces calories without sacrificing flavor."

    assert _processor(telemetry).scrub(text) == text
    assert telemetry.count == 0


def test_spanish_benign_text_is_verbatim() -> None:
    telemetry = InMemoryMedicalClaimTelemetry()
    text = "Un desayuno saludable y alto en proteína. Bajo en azúcar y delicioso."

    assert _processor(telemetry).scrub(text) == text
    assert telemetry.count == 0


# --- Each claim category is removed + recorded ---------------------------------------------------


def test_treatment_claim_is_removed() -> None:
    telemetry = InMemoryMedicalClaimTelemetry()

    result = _processor(telemetry).scrub("This meal cures diabetes. It tastes great.", source="r")

    assert result == "It tastes great."
    assert telemetry.categories == [MedicalClaimCategory.TREATMENT]
    assert telemetry.events[0].source == "r"


def test_prevention_claim_is_removed() -> None:
    telemetry = InMemoryMedicalClaimTelemetry()

    result = _processor(telemetry).scrub("Serve warm. Eating this prevents cancer.")

    assert result == "Serve warm."
    assert telemetry.count_for(MedicalClaimCategory.PREVENTION) == 1


def test_diagnosis_claim_is_removed() -> None:
    telemetry = InMemoryMedicalClaimTelemetry()

    result = _processor(telemetry).scrub("This dish will diagnose your condition. Enjoy.")

    assert result == "Enjoy."
    assert telemetry.count_for(MedicalClaimCategory.DIAGNOSIS) == 1


def test_authority_claim_is_removed() -> None:
    telemetry = InMemoryMedicalClaimTelemetry()

    result = _processor(telemetry).scrub("It is clinically proven. Bake for twenty minutes.")

    assert result == "Bake for twenty minutes."
    assert telemetry.count_for(MedicalClaimCategory.AUTHORITY) == 1


def test_effect_claim_is_removed() -> None:
    telemetry = InMemoryMedicalClaimTelemetry()

    result = _processor(telemetry).scrub("It lowers your blood pressure. Garnish with parsley.")

    assert result == "Garnish with parsley."
    assert telemetry.count_for(MedicalClaimCategory.EFFECT) == 1


def test_spanish_treatment_claim_is_removed() -> None:
    telemetry = InMemoryMedicalClaimTelemetry()

    result = _processor(telemetry).scrub("Esta receta cura la diabetes. Es deliciosa.")

    assert result == "Es deliciosa."
    assert telemetry.count_for(MedicalClaimCategory.TREATMENT) == 1


def test_spanish_effect_claim_is_removed() -> None:
    telemetry = InMemoryMedicalClaimTelemetry()

    result = _processor(telemetry).scrub("Reduce tu colesterol. Buen provecho.")

    assert result == "Buen provecho."
    assert telemetry.count_for(MedicalClaimCategory.EFFECT) == 1


# --- Multiple categories + record order ----------------------------------------------------------


def test_multiple_categories_recorded_in_stable_order() -> None:
    telemetry = InMemoryMedicalClaimTelemetry()
    text = "It lowers your cholesterol. This cures diabetes. It is medically proven. Serve hot."

    result = _processor(telemetry).scrub(text)

    assert result == "Serve hot."
    assert telemetry.categories == [
        MedicalClaimCategory.TREATMENT,
        MedicalClaimCategory.AUTHORITY,
        MedicalClaimCategory.EFFECT,
    ]


def test_a_category_is_recorded_once_even_if_it_fires_twice() -> None:
    telemetry = InMemoryMedicalClaimTelemetry()
    text = "This cures diabetes. That cures cancer. Mix and serve."

    result = _processor(telemetry).scrub(text)

    assert result == "Mix and serve."
    assert telemetry.categories == [MedicalClaimCategory.TREATMENT]


# --- Optional + iterable helpers -----------------------------------------------------------------


def test_scrub_optional_passes_none_through() -> None:
    assert _processor().scrub_optional(None) is None


def test_scrub_optional_collapses_to_none_when_emptied() -> None:
    assert _processor().scrub_optional("This cures cancer.") is None


def test_scrub_optional_keeps_benign_text() -> None:
    assert _processor().scrub_optional("Serve with rice.") == "Serve with rice."


def test_scrub_each_drops_steps_left_empty() -> None:
    steps = ["Mix the oats.", "This cures diabetes.", "Serve warm."]

    assert _processor().scrub_each(steps) == ("Mix the oats.", "Serve warm.")


def test_scrub_each_keeps_partial_steps() -> None:
    steps = ["Bake the dish. It is clinically proven."]

    assert _processor().scrub_each(steps) == ("Bake the dish.",)


# --- Adapters ------------------------------------------------------------------------------------


def test_logging_telemetry_emits_one_warning_per_claim(
    caplog: pytest.LogCaptureFixture,
) -> None:
    processor = ResponsePostProcessor(LoggingMedicalClaimTelemetry())

    with caplog.at_level(logging.WARNING, logger="app.guardrails.compliance"):
        processor.scrub("This cures diabetes. It lowers your cholesterol. Serve.")

    assert len(caplog.records) == 2
    assert all("medical claim removed" in record.message for record in caplog.records)


def test_default_processor_records_through_logging_adapter(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.guardrails.compliance"):
        ResponsePostProcessor().scrub("This cures diabetes. Serve hot.")

    assert len(caplog.records) == 1


def test_medical_claim_event_is_frozen() -> None:
    event = MedicalClaimEvent(source="reasoning", category=MedicalClaimCategory.TREATMENT)

    with pytest.raises(AttributeError):
        event.source = "other"  # type: ignore[misc]
