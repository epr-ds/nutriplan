"""The recommendation use case: prompt -> structured draft -> mapped recipes (AIA-203).

This is the application service behind ``POST /ai/recommendations``. It composes three
collaborators by constructor injection: the AIA-202 prompt assembler, the AIA-104
structured-completion loop (typed to :class:`RecommendationDraft`), and the AIA-203 recipe mapper.
Production wiring layers caching and budgets under the completion via
:func:`build_recommendation_service`; tests inject a fake-backed completion so the whole path runs
offline.
"""

from __future__ import annotations

from app.completions import build_cached_completion_service
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.llm.factory import build_client
from app.prompts.telemetry import PromptTelemetry
from app.prompts.types import Locale
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


class RecommendationService:
    """Produce recommended recipes for a command, in the requested locale."""

    def __init__(
        self,
        assembler: RecommendationPromptAssembler,
        completion: StructuredCompletion[RecommendationDraft],
        mapper: RecipeMapper,
    ) -> None:
        self._assembler = assembler
        self._completion = completion
        self._mapper = mapper

    def recommend(
        self,
        command: RecommendationCommand,
        *,
        locale: Locale | str = _DEFAULT_LOCALE,
    ) -> list[RecommendedRecipe]:
        """Assemble the prompt, ask the model for a draft, and map it onto recipes."""
        prompt = self._assembler.assemble(command, locale=locale)
        draft = self._completion.complete(prompt.to_request())
        return self._mapper.map(draft)


def _no_recommendations(_error: StructuredOutputError) -> RecommendationDraft:
    """Degrade to an empty recommendation set when the model never returns valid output."""
    return RecommendationDraft()


def build_recommendation_service(
    settings: Settings | None = None,
    *,
    catalogue: RecipeCatalogue | None = None,
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
    )
