"""Grade the golden corpus against the production safety filter and report regressions (AIA-704).

:class:`SafetyRegressionVerifier` drives each :class:`~app.regression.case.SafetyCase` through the
**production** :class:`~app.recommendations.safety.AllergenFilter` -- the very component the
recommendation service runs in ``_screen`` -- and checks three things per case:

* every expected-safe recipe survived (no over-removal);
* every other candidate was dropped (no allergen / exclusion slipped through);
* no surviving recipe still carries a forbidden ingredient fragment.

The forbidden-fragment check is deliberately filter-independent (a plain case-folded substring scan
over the surviving recipes' ingredients), so the corpus states the no-allergen guarantee directly
instead of trusting the filter to certify itself. A :class:`RegressionReport` collects the per-case
outcomes; its ``ok`` flag is the release gate -- any failure means an allergen or excluded
ingredient regressed, and the dedicated ``regression`` CI suite fails the change.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.recommendations.recipes import RecommendedRecipe
from app.recommendations.safety import AllergenFilter
from app.regression.case import CaseOutcome, SafetyCase


@dataclass(frozen=True, slots=True)
class RegressionReport:
    """The verdict over a whole corpus: the per-case outcomes and a single gate flag."""

    outcomes: tuple[CaseOutcome, ...]

    @property
    def ok(self) -> bool:
        """Whether every case passed -- the value the release gate keys on."""
        return all(outcome.ok for outcome in self.outcomes)

    @property
    def failures(self) -> tuple[str, ...]:
        """Every failure across the corpus, each prefixed with its case name."""
        return tuple(
            f"{outcome.name}: {failure}"
            for outcome in self.outcomes
            for failure in outcome.failures
        )


class SafetyRegressionVerifier:
    """Check a golden corpus against the production allergen / exclusion filter."""

    def __init__(self, safety_filter: AllergenFilter | None = None) -> None:
        self._filter = safety_filter or AllergenFilter()

    def verify(self, cases: tuple[SafetyCase, ...]) -> RegressionReport:
        """Run every case and collect the outcomes into a report."""
        return RegressionReport(tuple(self._verify_case(case) for case in cases))

    def _verify_case(self, case: SafetyCase) -> CaseOutcome:
        kept = self._filter.filter(case.recipes, allergies=case.allergies, excluded=case.excluded)
        kept_ids = tuple(recipe.id for recipe in kept)
        failures = (
            *self._missing_safe(case, kept_ids),
            *self._surviving_unsafe(case, kept_ids),
            *self._forbidden_leaks(case, kept),
        )
        return CaseOutcome(name=case.name, kept_ids=kept_ids, failures=failures)

    @staticmethod
    def _missing_safe(case: SafetyCase, kept_ids: tuple[str, ...]) -> tuple[str, ...]:
        kept = set(kept_ids)
        return tuple(
            f"expected-safe recipe {recipe_id!r} was dropped"
            for recipe_id in case.expected_safe_ids
            if recipe_id not in kept
        )

    @staticmethod
    def _surviving_unsafe(case: SafetyCase, kept_ids: tuple[str, ...]) -> tuple[str, ...]:
        safe = set(case.expected_safe_ids)
        return tuple(
            f"unsafe recipe {recipe_id!r} survived the filter"
            for recipe_id in kept_ids
            if recipe_id not in safe
        )

    @staticmethod
    def _forbidden_leaks(case: SafetyCase, kept: tuple[RecommendedRecipe, ...]) -> tuple[str, ...]:
        leaks: list[str] = []
        for recipe in kept:
            ingredients = " ".join(item.name for item in recipe.ingredients).casefold()
            leaks.extend(
                f"recipe {recipe.id!r} still contains forbidden {fragment!r}"
                for fragment in case.forbidden_substrings
                if fragment.casefold() in ingredients
            )
        return tuple(leaks)
