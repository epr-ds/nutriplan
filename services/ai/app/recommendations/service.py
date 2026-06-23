"""The recommendation use case: prompt -> structured draft -> mapped recipes + alignment.

This is the application service behind ``POST /ai/recommendations``. It composes its collaborators
by constructor injection: the AIA-202 prompt assembler, the AIA-104 structured-completion loop
(typed to :class:`RecommendationDraft`), the AIA-203 recipe mapper, and the AIA-204 aligner. The
result bundles the mapped recipes with the model's ``reasoning`` and a deterministic
``nutritionalAlignment`` (scored via AIA-106). Production wiring layers caching and budgets under
the completion via :func:`build_recommendation_service`; tests inject a fake-backed completion so
the whole path runs offline.
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
    ) -> None:
        self._assembler = assembler
        self._completion = completion
        self._mapper = mapper
        self._aligner = aligner or RecommendationAligner()

    def recommend(
        self,
        command: RecommendationCommand,
        *,
        locale: Locale | str = _DEFAULT_LOCALE,
    ) -> RecommendationResult:
        """Assemble the prompt, ask the model for a draft, map recipes, and score alignment."""
        prompt = self._assembler.assemble(command, locale=locale)
        draft = self._completion.complete(prompt.to_request())
        recipes = tuple(self._mapper.map(draft))
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
    telemetry: PromptTelemetry | None = None,
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
    )
