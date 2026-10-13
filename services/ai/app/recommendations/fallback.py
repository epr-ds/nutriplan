"""Hallucination detection + curated-recipe fallback (AIA-503).

"I get a safe result even when the model misbehaves." Three things can leave the recommendation
pipeline with nothing to show the user: the model returns an empty / unparseable draft (AIA-104
already degrades that to an empty draft), it returns recipes that the allergy (AIA-501) and bounds
(AIA-502) guards strip away, or it returns hallucinated stubs with no ingredients or steps. In every
case the honest-but-useless answer is an empty list. :class:`CuratedRecipeFallback` detects that
the model produced nothing usable and substitutes **curated catalogue recipes** instead -- the
production source is the P2 recipe search (DPL-202); tests and offline runs use
:class:`InMemoryCuratedRecipeSource`.

Curated recipes are *not* blindly trusted: the caller passes a ``screen`` (the same safety + bounds
checks the model output went through) so a fallback can never reintroduce an allergen or an
out-of-bounds recipe for *this* user. Every request and every fallback is recorded through a
:class:`FallbackTelemetry` port, which makes the **fallback rate** a first-class metric (AC3).
Everything here is pure -- no LLM, no I/O -- so it is fully unit-testable and feeds the AIA-506
adversarial suite.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from app.recommendations.commands import RecommendationCommand
from app.recommendations.recipes import RecommendedRecipe

_LOGGER = logging.getLogger("app.recommendations.fallback")

# A recipe that screens applied to curated candidates: safety (AIA-501) + bounds (AIA-502).
RecipeScreen = Callable[[tuple[RecommendedRecipe, ...]], tuple[RecommendedRecipe, ...]]


class FallbackReason(StrEnum):
    """Why the recommender fell back to curated recipes."""

    EMPTY_OUTPUT = "empty_output"
    """The model returned no recipes at all (empty/unparseable draft, or low confidence)."""

    UNUSABLE_OUTPUT = "unusable_output"
    """The model returned recipes, but none survived the validity / safety / bounds checks."""


@dataclass(frozen=True, slots=True)
class FallbackEvent:
    """A single fallback occurrence -- the unit the telemetry counts toward the fallback rate."""

    reason: FallbackReason
    model_count: int
    curated_count: int


@runtime_checkable
class CuratedRecipeSource(Protocol):
    """A read port over curated catalogue recipes (production: the P2 DPL-202 recipe search)."""

    def search(
        self, command: RecommendationCommand, *, limit: int
    ) -> tuple[RecommendedRecipe, ...]:
        """Return up to ``limit`` curated recipes that fit the command's constraints."""
        ...


def _matches_diet(recipe: RecommendedRecipe, diet_type: str | None) -> bool:
    """Keep a recipe when the diet is unset, the recipe is diet-agnostic, or it declares it."""
    if diet_type is None or not recipe.dietary_types:
        return True
    return diet_type.casefold() in {value.casefold() for value in recipe.dietary_types}


class InMemoryCuratedRecipeSource:
    """A network-free :class:`CuratedRecipeSource` over a fixed list, honoring diet + limit."""

    def __init__(self, recipes: Iterable[RecommendedRecipe] = ()) -> None:
        self._recipes: tuple[RecommendedRecipe, ...] = tuple(recipes)

    def search(
        self, command: RecommendationCommand, *, limit: int
    ) -> tuple[RecommendedRecipe, ...]:
        matching = [recipe for recipe in self._recipes if _matches_diet(recipe, command.diet_type)]
        return tuple(matching[:limit])


@runtime_checkable
class FallbackTelemetry(Protocol):
    """A write port: record every recommendation request and every fallback to curated recipes."""

    def record_request(self) -> None: ...

    def record_fallback(self, event: FallbackEvent) -> None: ...


class InMemoryFallbackTelemetry:
    """Counts requests and fallbacks so the fallback *rate* can be asserted and reported."""

    def __init__(self) -> None:
        self.requests = 0
        self.events: list[FallbackEvent] = []

    def record_request(self) -> None:
        self.requests += 1

    def record_fallback(self, event: FallbackEvent) -> None:
        self.events.append(event)

    @property
    def fallback_count(self) -> int:
        """How many requests fell back to curated recipes."""
        return len(self.events)

    @property
    def rate(self) -> float:
        """The fraction of requests that fell back -- 0.0 when there have been no requests."""
        if self.requests == 0:
            return 0.0
        return self.fallback_count / self.requests


class LoggingFallbackTelemetry:
    """Logs each fallback at WARNING -- the model failed to produce a usable answer."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or _LOGGER

    def record_request(self) -> None:
        # Requests are not logged individually; the fallback rate is derived from a metrics adapter.
        return None

    def record_fallback(self, event: FallbackEvent) -> None:
        self._logger.warning(
            "recommendation fell back to curated recipes (reason=%s, model=%s, curated=%s)",
            event.reason.value,
            event.model_count,
            event.curated_count,
        )


def _is_well_formed(recipe: RecommendedRecipe) -> bool:
    """A usable recipe has at least one ingredient and one step; otherwise it is a stub."""
    return bool(recipe.ingredients) and bool(recipe.instructions)


class CuratedRecipeFallback:
    """Detect unusable model output and substitute screened curated catalogue recipes."""

    def __init__(
        self,
        source: CuratedRecipeSource | None = None,
        telemetry: FallbackTelemetry | None = None,
    ) -> None:
        self._source = source or InMemoryCuratedRecipeSource()
        self._telemetry = telemetry or LoggingFallbackTelemetry()

    def resolve(
        self,
        model_recipes: tuple[RecommendedRecipe, ...],
        command: RecommendationCommand,
        *,
        mapped_count: int,
        screen: RecipeScreen,
    ) -> tuple[RecommendedRecipe, ...]:
        """Return the model's usable recipes, or curated recipes when it produced none.

        ``model_recipes`` are the model's recipes after the safety + bounds screen; ``mapped_count``
        is how many recipes the model originally produced (so an empty result can be reported as a
        genuinely empty draft vs. recipes that were all rejected). ``screen`` is applied to any
        curated substitutes so they are held to the same safety/bounds standard as the model output.
        """
        self._telemetry.record_request()

        usable = tuple(recipe for recipe in model_recipes if _is_well_formed(recipe))
        if usable:
            return usable

        candidates = self._source.search(command, limit=command.count)
        curated = tuple(recipe for recipe in screen(candidates) if _is_well_formed(recipe))[
            : command.count
        ]
        reason = (
            FallbackReason.EMPTY_OUTPUT if mapped_count == 0 else FallbackReason.UNUSABLE_OUTPUT
        )
        self._telemetry.record_fallback(
            FallbackEvent(reason=reason, model_count=mapped_count, curated_count=len(curated))
        )
        return curated
