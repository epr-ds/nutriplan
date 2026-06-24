"""The meal-analysis use case (AIA-302, AIA-303): nutrition + alignment + warnings.

This is the application service behind ``POST /ai/analyze-meal``. AIA-301 established the transport
seam; AIA-302 fills it by constructor-injecting the analyze-meal prompt assembler, the AIA-104
structured-completion loop (typed to :class:`NutritionEstimateDraft`), and a meal aligner. It
assembles a localized prompt, asks the model for a schema-constrained estimate, normalizes it onto
:class:`AnalyzedNutrition`, and scores it against a balanced-meal reference (reusing AIA-106).
AIA-303 then builds the localized advisory warnings -- low confidence, nutrients well over/under the
reference, and detected allergens. Production wiring layers caching and budgets under the completion
via :func:`build_meal_analysis_service`; tests inject a fake-backed completion so the path runs
offline.
"""

from __future__ import annotations

from app.analysis.alignment import MealAligner
from app.analysis.assembler import MealAnalysisPromptAssembler, build_meal_analysis_prompt_assembler
from app.analysis.commands import MealAnalysisCommand
from app.analysis.draft import NutritionEstimateDraft
from app.analysis.normalize import clamp_confidence, is_low_confidence, normalize_estimate
from app.analysis.result import AnalyzedNutrition, MealAnalysis
from app.analysis.warnings import build_warnings, localize_all
from app.completions import build_cached_completion_service
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.llm.factory import build_client
from app.prompts.telemetry import PromptTelemetry
from app.prompts.types import Locale
from app.structured.errors import StructuredOutputError
from app.structured.parser import StructuredOutputParser
from app.structured.service import StructuredCompletion

_DEFAULT_LOCALE = Locale.default()
_DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.5


class MealAnalysisService:
    """Estimate a described meal's nutrition, score its alignment, and flag low confidence."""

    def __init__(
        self,
        completion: StructuredCompletion[NutritionEstimateDraft],
        *,
        assembler: MealAnalysisPromptAssembler | None = None,
        aligner: MealAligner | None = None,
        low_confidence_threshold: float = _DEFAULT_LOW_CONFIDENCE_THRESHOLD,
    ) -> None:
        self._completion = completion
        self._assembler = assembler or build_meal_analysis_prompt_assembler()
        self._aligner = aligner or MealAligner()
        self._low_confidence_threshold = low_confidence_threshold

    def analyze(
        self,
        command: MealAnalysisCommand,
        *,
        locale: Locale | str = _DEFAULT_LOCALE,
    ) -> MealAnalysis:
        """Assemble the prompt, ask the model for an estimate, normalize, score, and flag."""
        resolved = Locale.parse(locale, default=Locale.default())
        prompt = self._assembler.assemble(command, locale=resolved)
        draft = self._completion.complete(prompt.to_request())
        nutrition = normalize_estimate(draft)
        alignment = self._aligner.align(nutrition)
        warnings = self._warnings(draft, nutrition, resolved)
        return MealAnalysis(nutrition=nutrition, alignment=alignment, warnings=warnings)

    def _warnings(
        self,
        draft: NutritionEstimateDraft,
        nutrition: AnalyzedNutrition | None,
        locale: Locale,
    ) -> tuple[str, ...]:
        """Build the localized advisories: low confidence, over/under target, and allergens."""
        findings = build_warnings(
            low_confidence=is_low_confidence(
                confidence=clamp_confidence(draft.confidence),
                nutrition=nutrition,
                threshold=self._low_confidence_threshold,
            ),
            nutrition=nutrition,
            reference=self._aligner.reference,
            allergens=draft.allergens,
        )
        return localize_all(findings, locale)


def _empty_estimate(_error: StructuredOutputError) -> NutritionEstimateDraft:
    """Degrade to an empty estimate when the model never returns valid output."""
    return NutritionEstimateDraft()


def build_meal_analysis_service(
    settings: Settings | None = None,
    *,
    aligner: MealAligner | None = None,
    telemetry: PromptTelemetry | None = None,
) -> MealAnalysisService:
    """Wire the service from configuration: cached, budgeted, schema-constrained completions."""
    settings = settings or default_settings
    base = build_cached_completion_service(build_client(settings), settings)
    completion: StructuredCompletion[NutritionEstimateDraft] = StructuredCompletion(
        base,
        StructuredOutputParser(NutritionEstimateDraft),
        max_attempts=2,
        fallback=_empty_estimate,
    )
    return MealAnalysisService(
        completion,
        assembler=build_meal_analysis_prompt_assembler(telemetry=telemetry),
        aligner=aligner or MealAligner(),
    )
