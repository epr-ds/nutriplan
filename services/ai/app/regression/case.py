"""Value objects for the allergy / exclusion regression corpus (AIA-704).

A :class:`SafetyCase` is one golden constraint scenario: the caller's allergies and excluded
ingredients, a set of candidate recipes (some deliberately unsafe), and the exact ids that must
survive the production safety filter. ``forbidden_substrings`` are ingredient fragments that must
never appear in any surviving recipe -- a filter-independent statement of the no-allergen guarantee,
so the corpus asserts safety directly rather than trusting the filter to grade its own output.

A :class:`CaseOutcome` is the verifier's verdict for one case: what survived and what (if anything)
went wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.recommendations.recipes import RecommendedRecipe


@dataclass(frozen=True, slots=True)
class SafetyCase:
    """One golden constraint scenario the safety filter must satisfy on every run."""

    name: str
    allergies: tuple[str, ...]
    excluded: tuple[str, ...]
    recipes: tuple[RecommendedRecipe, ...]
    expected_safe_ids: tuple[str, ...]
    forbidden_substrings: tuple[str, ...]

    @property
    def expected_unsafe_ids(self) -> tuple[str, ...]:
        """Recipe ids that must be removed: every candidate not in the expected-safe set."""
        safe = set(self.expected_safe_ids)
        return tuple(recipe.id for recipe in self.recipes if recipe.id not in safe)


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    """The verifier's verdict for one :class:`SafetyCase`."""

    name: str
    kept_ids: tuple[str, ...]
    failures: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """Whether the case passed with no failures."""
        return not self.failures
