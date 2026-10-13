"""The headline result of an eval run: the two quality metrics, plus per-case detail (AIA-701).

A run produces an :class:`EvalReport` over a set of :class:`~app.eval.case.CaseResult`. It exposes
the two numbers AIA-701 asks for, computed over the flat population of graded recipes so they are
consistent with one another:

- **constraint-respect** -- the share of recipes with no hard-constraint violation (right diet, no
  excluded ingredient). This is the safety/obedience rate of the AI's output.
- **mean alignment** -- the mean per-recipe nutritional-alignment score (0-1), i.e. how closely the
  output hits the calorie/macro targets.

Everything is derived from the cases (no duplicated state), and :meth:`metrics` /
:meth:`to_dict` are JSON-friendly so a headless run can print results and append them to a history
file for trending over time.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.eval.case import CaseResult


@dataclass(frozen=True, slots=True)
class EvalReport:
    """The metrics for one eval run, projected from its per-case results."""

    generated_at: str
    cases: tuple[CaseResult, ...]

    @property
    def total_cases(self) -> int:
        return len(self.cases)

    @property
    def respected_cases(self) -> int:
        """Cases where every recipe respected the constraints."""
        return sum(1 for case in self.cases if case.respected)

    @property
    def total_recipes(self) -> int:
        return sum(case.total_recipes for case in self.cases)

    @property
    def respected_recipes(self) -> int:
        return sum(case.respected_recipes for case in self.cases)

    @property
    def constraint_respect(self) -> float:
        """Share of recipes with no hard-constraint violation (0-1)."""
        if self.total_recipes == 0:
            return 0.0
        return round(self.respected_recipes / self.total_recipes, 4)

    @property
    def constraint_respect_pct(self) -> float:
        return round(self.constraint_respect * 100, 2)

    @property
    def mean_alignment(self) -> float:
        """Mean per-recipe alignment score across the whole eval set (0-1)."""
        scores = [
            recipe.alignment.score for case in self.cases for recipe in case.alignment.recipes
        ]
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 4)

    @property
    def mean_alignment_pct(self) -> float:
        return round(self.mean_alignment * 100, 2)

    def summary(self) -> str:
        """A one-line, log-friendly headline of the run."""
        return (
            f"Eval {self.generated_at}: {self.total_cases} prompts / {self.total_recipes} recipes "
            f"-- constraint-respect {self.constraint_respect_pct}% "
            f"-- mean alignment {self.mean_alignment_pct}%"
        )

    def metrics(self) -> dict[str, object]:
        """The compact, trendable record appended to history (no per-case detail)."""
        return {
            "generated_at": self.generated_at,
            "total_cases": self.total_cases,
            "total_recipes": self.total_recipes,
            "respected_recipes": self.respected_recipes,
            "constraint_respect": self.constraint_respect,
            "mean_alignment": self.mean_alignment,
        }

    def to_dict(self) -> dict[str, object]:
        """The full report: headline metrics plus a per-case, per-recipe breakdown."""
        return {
            **self.metrics(),
            "respected_cases": self.respected_cases,
            "constraint_respect_pct": self.constraint_respect_pct,
            "mean_alignment_pct": self.mean_alignment_pct,
            "cases": [
                {
                    "name": case.name,
                    "prompt": case.prompt,
                    "respected": case.respected,
                    "score": case.score,
                    "aligned_count": case.alignment.aligned_count,
                    "total_recipes": case.total_recipes,
                    "respected_recipes": case.respected_recipes,
                    "recipes": [
                        {
                            "recipe": recipe.recipe_name,
                            "score": recipe.alignment.score,
                            "aligned": recipe.alignment.aligned,
                            "violations": list(recipe.alignment.violations),
                        }
                        for recipe in case.alignment.recipes
                    ],
                }
                for case in self.cases
            ],
        }
