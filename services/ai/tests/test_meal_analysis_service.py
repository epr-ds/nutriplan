"""End-to-end tests for the meal-analysis application service (AIA-302).

The service ties the analyze-meal prompt assembler to the AIA-104 structured-completion loop, then
normalizes the model's estimate, scores it against a balanced-meal reference (reusing AIA-106), and
flags low-confidence estimates. The LLM is the network-free :class:`FakeLLMProvider`, so the whole
path runs offline; a scripted draft stands in for the model's reply.
"""

from __future__ import annotations

import json

from app.analysis.alignment import MealAligner, MealReference
from app.analysis.commands import MealAnalysisCommand, MealIngredient
from app.analysis.draft import NutritionEstimateDraft
from app.analysis.result import AnalyzedNutrition
from app.analysis.service import MealAnalysisService, build_meal_analysis_service
from app.core.config import Settings
from app.llm.client import LLMClient
from app.llm.fake import FakeLLMProvider
from app.llm.retry import RetryPolicy
from app.llm.types import LLMResponse, Role
from app.prompts.types import Locale
from app.structured.parser import StructuredOutputParser
from app.structured.service import StructuredCompletion

_DRAFT = {"calories": 500, "protein": 20, "carbs": 60, "fat": 18, "sugar": 12, "confidence": 0.85}

_COMMAND = MealAnalysisCommand(
    description="Oatmeal with banana and peanut butter",
    ingredients=(MealIngredient(name="oats", quantity=80, unit="g"),),
)


def _response(text: str) -> LLMResponse:
    return LLMResponse(content=text, model="fake")


def _service(
    provider: FakeLLMProvider,
    *,
    aligner: MealAligner | None = None,
    fallback=None,
    max_attempts: int = 1,
    low_confidence_threshold: float = 0.5,
) -> MealAnalysisService:
    client = LLMClient(provider, RetryPolicy(max_retries=0))
    completion = StructuredCompletion(
        client,
        StructuredOutputParser(NutritionEstimateDraft),
        max_attempts=max_attempts,
        fallback=fallback,
    )
    return MealAnalysisService(
        completion=completion,
        aligner=aligner,
        low_confidence_threshold=low_confidence_threshold,
    )


def test_estimate_is_normalized_to_nutrition() -> None:
    service = _service(FakeLLMProvider([_response(json.dumps(_DRAFT))]))

    result = service.analyze(_COMMAND)

    assert result.nutrition == AnalyzedNutrition(
        calories=500, protein=20, carbs=60, fat=18, sugar=12
    )


def test_request_carries_assembled_prompt_and_schema_constraint() -> None:
    provider = FakeLLMProvider([_response(json.dumps(_DRAFT))])

    _service(provider).analyze(_COMMAND)

    call = provider.calls[0]
    assert any(m.role is Role.SYSTEM and "registered-dietitian" in m.content for m in call.messages)
    assert call.response_format is not None
    assert call.response_format.name == "NutritionEstimateDraft"


def test_alignment_is_computed_against_the_reference() -> None:
    # A reference identical to the estimate yields a perfect alignment (AC2 reuses AIA-106).
    reference = MealReference(calories=500, protein=20, carbs=60, fat=18, sugar=12)
    service = _service(
        FakeLLMProvider([_response(json.dumps(_DRAFT))]),
        aligner=MealAligner(reference=reference),
    )

    result = service.analyze(_COMMAND)

    assert result.alignment is not None
    assert result.alignment.percentage == 100.0


def test_high_confidence_estimate_raises_no_warning() -> None:
    service = _service(FakeLLMProvider([_response(json.dumps(_DRAFT))]))

    result = service.analyze(_COMMAND)

    assert result.warnings == ()


def test_low_confidence_estimate_is_flagged() -> None:
    draft = {**_DRAFT, "confidence": 0.3}
    service = _service(FakeLLMProvider([_response(json.dumps(draft))]))

    result = service.analyze(_COMMAND)

    assert any("confidence" in warning.lower() for warning in result.warnings)


def test_low_confidence_warning_is_localized() -> None:
    draft = {**_DRAFT, "confidence": 0.2}
    service = _service(FakeLLMProvider([_response(json.dumps(draft))]))

    result = service.analyze(_COMMAND, locale=Locale.ES)

    assert any("confianza" in warning.lower() for warning in result.warnings)


def test_unestimable_meal_yields_no_nutrition_but_flags_confidence() -> None:
    # The model returned nothing usable: degrade to an empty estimate via the fallback.
    service = _service(
        FakeLLMProvider([_response("not json at all")]),
        fallback=lambda _error: NutritionEstimateDraft(),
    )

    result = service.analyze(_COMMAND)

    assert result.nutrition is None
    assert result.alignment is None
    assert any("confidence" in warning.lower() for warning in result.warnings)


def test_factory_builds_a_service() -> None:
    service = build_meal_analysis_service(Settings(llm_provider="fake"))

    assert isinstance(service, MealAnalysisService)
