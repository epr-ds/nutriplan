"""HRD-103 — Privacy & data compliance: consent-gated meal-health processing.

Before a user's meal-health data is sent to an LLM provider for analysis, the user must
have consented (HRD-103 — Privacy & data compliance (MX LFPDPPP): data map, retention,
consent). The analysis use case owns that boundary: with consent withheld, the completion
engine must not be invoked at all.
"""

from __future__ import annotations

import json

from app.analysis.alignment import MealAligner
from app.analysis.commands import MealAnalysisCommand, MealIngredient
from app.analysis.draft import NutritionEstimateDraft
from app.analysis.service import MealAnalysisService
from app.guardrails.compliance import ResponsePostProcessor
from app.guardrails.sanitizer import PromptSanitizer
from app.llm.client import LLMClient
from app.llm.fake import FakeLLMProvider
from app.llm.retry import RetryPolicy
from app.llm.types import LLMResponse
from app.prompts.types import Locale
from app.structured.parser import StructuredOutputParser
from app.structured.service import StructuredCompletion

_DRAFT = {"calories": 500, "protein": 20, "carbs": 60, "fat": 18, "sugar": 12, "confidence": 0.85}

_COMMAND = MealAnalysisCommand(
    description="Oatmeal with banana and peanut butter",
    ingredients=(MealIngredient(name="oats", quantity=80, unit="g"),),
)


class _RecordingCompletion(StructuredCompletion[NutritionEstimateDraft]):
    """Completion stand-in that records whether the LLM path was used."""

    def __init__(self, provider: FakeLLMProvider | None = None) -> None:
        super().__init__(
            client=LLMClient(provider or FakeLLMProvider(), RetryPolicy(max_retries=0)),
            parser=StructuredOutputParser(NutritionEstimateDraft),
            max_attempts=1,
        )
        self.invoked = 0

    def complete(self, request) -> NutritionEstimateDraft:  # type: ignore[override]
        self.invoked += 1
        return super().complete(request)


def _service(
    *, consent: bool = False, provider: FakeLLMProvider | None = None
) -> MealAnalysisService:
    return MealAnalysisService(
        completion=_RecordingCompletion(provider=provider),
        aligner=MealAligner(),
        low_confidence_threshold=0.5,
        consent=consent,
        sanitizer=PromptSanitizer(),
        post_processor=ResponsePostProcessor(),
    )


def test_analyze_does_not_invoke_llm_without_user_consent() -> None:
    """With consent withheld, health-data processing must not reach the LLM."""
    service = _service()
    result = service.analyze(_COMMAND, locale=Locale.EN)

    assert service._completion.invoked == 0
    # The unconsented analysis degrades to an unestimated result, not a fabricated estimate.
    assert result.nutrition is None
    assert result.alignment is None
    assert result.disclaimer is not None
    assert "not medical advice" in result.disclaimer


def test_analyze_invokes_llm_with_user_consent() -> None:
    """With consent granted, the meal-health data is processed through the completion engine."""
    service = _service(
        consent=True,
        provider=FakeLLMProvider([LLMResponse(content=json.dumps(_DRAFT), model="fake")]),
    )

    result = service.analyze(_COMMAND, locale=Locale.EN)

    assert service._completion.invoked == 1
    assert result.nutrition is not None
    assert result.nutrition.calories == 500
