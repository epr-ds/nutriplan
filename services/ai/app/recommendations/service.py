"""The recommendation use case: prompt -> draft -> mapped, diversified recipes + alignment.

This is the application service behind ``POST /ai/recommendations``. It composes its collaborators
by constructor injection: the AIA-202 prompt assembler, the AIA-104 structured-completion loop
(typed to :class:`RecommendationDraft`), the AIA-203 recipe mapper, the AIA-205 diversifier, and the
AIA-204 aligner. The result bundles the mapped recipes with the model's ``reasoning`` and a
deterministic ``nutritionalAlignment`` (scored via AIA-106). The diversifier runs after mapping and
before scoring so alignment reflects exactly the set the user will see. An AIA-501
:class:`~app.recommendations.safety.AllergenFilter` runs right after mapping -- before diversifying
or scoring -- to drop any recipe that violates the caller's allergies or excluded ingredients, so an
unsafe recipe never reaches the user even if the model ignored the prompt. Production wiring layers
caching and budgets under the completion via :func:`build_recommendation_service`; tests inject a
fake-backed completion so the whole path runs offline.

Before any of that, the AIA-502 :class:`~app.recommendations.bounds.NutritionBoundsGuard` clamps the
command's calorie targets into sane bounds (so the prompt and alignment work from real numbers), and
after the safety filter it rejects any mapped recipe whose nutrition is physically impossible -- a
last deterministic check on the model's own output before the user sees it.

Finally, the AIA-503 :class:`~app.recommendations.fallback.CuratedRecipeFallback` closes the loop:
when the model produces nothing usable -- an empty draft, or recipes the safety/bounds/validity
checks strip away -- it substitutes curated catalogue recipes (screened for the same caller, so a
fallback can never reintroduce an allergen) and records the fallback so its rate can be tracked. It
runs on the screened model output before diversifying, so an unusable answer degrades to a safe one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.completions import build_cached_completion_service
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.llm.factory import build_client
from app.prompts.telemetry import PromptTelemetry
from app.prompts.types import Locale
from app.recommendations.alignment import RecommendationAligner, RecommendationAlignment
from app.recommendations.assembler import (
    RecommendationPromptAssembler,
    build_recommendation_prompt_assembler,
)
from app.recommendations.bounds import (
    BoundsTelemetry,
    LoggingBoundsTelemetry,
    NutritionBoundsGuard,
)
from app.recommendations.catalogue import InMemoryRecipeCatalogue, RecipeCatalogue
from app.recommendations.commands import RecommendationCommand
from app.recommendations.draft import RecommendationDraft
from app.recommendations.fallback import (
    CuratedRecipeFallback,
    CuratedRecipeSource,
    FallbackTelemetry,
    LoggingFallbackTelemetry,
)
from app.recommendations.mapper import RecipeMapper
from app.recommendations.recipes import RecommendedRecipe
from app.recommendations.safety import AllergenFilter, GuardrailTelemetry, LoggingGuardrailTelemetry
from app.recommendations.variety import RecommendationDiversifier, VarietyPolicy
from app.structured.errors import StructuredOutputError
from app.structured.parser import StructuredOutputParser
from app.structured.service import StructuredCompletion

_DEFAULT_LOCALE = Locale.default()


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    """Everything the recommendation use case produces for one request.

    ``alignment`` is ``None`` when there is nothing to score against (no targets and no hard
    preferences); ``reasoning`` is ``None`` when the model did not provide one.
    """

    recipes: tuple[RecommendedRecipe, ...]
    reasoning: str | None = None
    alignment: RecommendationAlignment | None = None


class RecommendationService:
    """Produce recommended recipes (with reasoning + alignment) for a command and locale."""

    def __init__(
        self,
        assembler: RecommendationPromptAssembler,
        completion: StructuredCompletion[RecommendationDraft],
        mapper: RecipeMapper,
        aligner: RecommendationAligner | None = None,
        diversifier: RecommendationDiversifier | None = None,
        safety_filter: AllergenFilter | None = None,
        bounds_guard: NutritionBoundsGuard | None = None,
        fallback: CuratedRecipeFallback | None = None,
    ) -> None:
        self._assembler = assembler
        self._completion = completion
        self._mapper = mapper
        self._aligner = aligner or RecommendationAligner()
        self._diversifier = diversifier or RecommendationDiversifier()
        self._safety_filter = safety_filter or AllergenFilter()
        self._bounds_guard = bounds_guard or NutritionBoundsGuard()
        self._fallback = fallback or CuratedRecipeFallback()

    def recommend(
        self,
        command: RecommendationCommand,
        *,
        locale: Locale | str = _DEFAULT_LOCALE,
    ) -> RecommendationResult:
        """Clamp targets, prompt, screen for safety + bounds, fall back if unusable, diversify."""
        command = self._bounds_guard.clamp(command)
        prompt = self._assembler.assemble(command, locale=locale)
        draft = self._completion.complete(prompt.to_request())
        mapped = self._mapper.map(draft)
        screened = self._screen(tuple(mapped), command)
        resolved = self._fallback.resolve(
            screened,
            command,
            mapped_count=len(mapped),
            screen=lambda candidates: self._screen(candidates, command),
        )
        recipes = tuple(
            self._diversifier.diversify(
                resolved,
                previous_meals=command.previous_meals,
                limit=command.count,
            )
        )
        alignment = self._aligner.align(recipes, command)
        return RecommendationResult(
            recipes=recipes,
            reasoning=draft.reasoning,
            alignment=alignment,
        )

    def _screen(
        self, recipes: Sequence[RecommendedRecipe], command: RecommendationCommand
    ) -> tuple[RecommendedRecipe, ...]:
        """Apply the allergy (AIA-501) and bounds (AIA-502) guards to a set of recipes."""
        safe = self._safety_filter.filter(
            tuple(recipes),
            allergies=command.allergies,
            excluded=command.excluded_ingredients,
        )
        return self._bounds_guard.enforce(safe)


def _no_recommendations(_error: StructuredOutputError) -> RecommendationDraft:
    """Degrade to an empty recommendation set when the model never returns valid output."""
    return RecommendationDraft()


def build_recommendation_service(
    settings: Settings | None = None,
    *,
    catalogue: RecipeCatalogue | None = None,
    aligner: RecommendationAligner | None = None,
    diversifier: RecommendationDiversifier | None = None,
    telemetry: PromptTelemetry | None = None,
    guardrail_telemetry: GuardrailTelemetry | None = None,
    bounds_telemetry: BoundsTelemetry | None = None,
    curated_source: CuratedRecipeSource | None = None,
    fallback_telemetry: FallbackTelemetry | None = None,
) -> RecommendationService:
    """Wire the service from configuration: cached, budgeted, schema-constrained completions."""
    settings = settings or default_settings
    base = build_cached_completion_service(build_client(settings), settings)
    completion: StructuredCompletion[RecommendationDraft] = StructuredCompletion(
        base,
        StructuredOutputParser(RecommendationDraft),
        max_attempts=2,
        fallback=_no_recommendations,
    )
    return RecommendationService(
        build_recommendation_prompt_assembler(telemetry=telemetry),
        completion,
        RecipeMapper(catalogue or InMemoryRecipeCatalogue()),
        aligner or RecommendationAligner(),
        diversifier
        or RecommendationDiversifier(VarietyPolicy.from_strength(settings.variety_strength)),
        AllergenFilter(guardrail_telemetry or LoggingGuardrailTelemetry()),
        NutritionBoundsGuard(bounds_telemetry or LoggingBoundsTelemetry()),
        CuratedRecipeFallback(curated_source, fallback_telemetry or LoggingFallbackTelemetry()),
    )
