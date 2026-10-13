"""The unit of the offline eval harness: a fixed prompt with known constraints (AIA-701).

An :class:`EvalCase` is one scenario on the eval set -- a human-readable ``prompt``, the
:class:`~app.recommendations.commands.RecommendationCommand` that carries its *known constraints*
(diet, allergies/exclusions, calorie/macro targets), and the recorded model output (``recipes``)
to grade against them. The harness scores each case with the production
:class:`~app.recommendations.alignment.RecommendationAligner`, yielding a :class:`CaseResult` that
reuses the same per-recipe :class:`~app.scoring.types.NutritionalAlignment` the API exposes as
``nutritionalAlignment``.

"Respect" is read off the scorer's hard-preference gate: a recipe respects the case's constraints
when it has **no** violations (right diet, no excluded ingredient). That is deliberately the same
notion of a violation the live recommendation flow uses, so the eval measures the real policy.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.recommendations.alignment import RecommendationAlignment
from app.recommendations.commands import RecommendationCommand
from app.recommendations.recipes import RecommendedRecipe


@dataclass(frozen=True, slots=True)
class EvalCase:
    """A fixed prompt, its known constraints (the command), and the output to grade."""

    name: str
    prompt: str
    command: RecommendationCommand
    recipes: tuple[RecommendedRecipe, ...]


@dataclass(frozen=True, slots=True)
class CaseResult:
    """One graded case: its overall alignment plus what respected the constraints."""

    name: str
    prompt: str
    alignment: RecommendationAlignment

    @property
    def score(self) -> float:
        """The case's mean alignment score across its recipes (0-1)."""
        return self.alignment.score

    @property
    def total_recipes(self) -> int:
        """How many recipes the case produced."""
        return self.alignment.total

    @property
    def respected_recipes(self) -> int:
        """How many of the case's recipes have no hard-constraint violation."""
        return sum(1 for recipe in self.alignment.recipes if not recipe.alignment.violations)

    @property
    def respected(self) -> bool:
        """Whether *every* recipe in the case respected the constraints."""
        return self.respected_recipes == self.total_recipes
