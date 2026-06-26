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
"""

from __future__ import annotations

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
from app.recommendations.catalogue import InMemoryRecipeCatalogue, RecipeCatalogue
from app.recommendations.commands import RecommendationCommand
from app.recommendations.draft import RecommendationDraft
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
    ) -> None:
        self._assembler = assembler
        self._completion = completion
        self._mapper = mapper
        self._aligner = aligner or RecommendationAligner()
        self._diversifier = diversifier or RecommendationDiversifier()
        self._safety_filter = safety_filter or AllergenFilter()

    def recommend(
        self,
        command: RecommendationCommand,
        *,
        locale: Locale | str = _DEFAULT_LOCALE,
    ) -> RecommendationResult:
        """Assemble the prompt, get a draft, map recipes, enforce allergies, diversify, score."""
        prompt = self._assembler.assemble(command, locale=locale)
        draft = self._completion.complete(prompt.to_request())
        mapped = self._mapper.map(draft)
        safe = self._safety_filter.filter(
            tuple(mapped),
            allergies=command.allergies,
            excluded=command.excluded_ingredients,
        )
        recipes = tuple(
            self._diversifier.diversify(
                safe,
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
    )
