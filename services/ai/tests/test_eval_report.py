"""Unit tests for the eval report's metrics and serialization (AIA-701).

The report projects the two headline metrics off its cases and serializes them for a headless run.
These tests pin the percentages, the empty-set guards (no division by zero), and the JSON shape that
feeds both the printed report and the trend history.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.eval.case import EvalCase
from app.eval.harness import EvalHarness
from app.eval.report import EvalReport
from app.recommendations.commands import RecommendationCommand, RecommendationContext
from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)

_FIXED = datetime(2026, 6, 25, 12, 0, 0, tzinfo=UTC)


def _recipe(name: str, *, calories: int, ingredients: tuple[str, ...] = ()) -> RecommendedRecipe:
    return RecommendedRecipe(
        id=name.casefold().replace(" ", "-"),
        name=name,
        servings=1,
        ingredients=tuple(RecommendedIngredient(name=item) for item in ingredients),
        instructions=("step",),
        nutrition=RecommendedNutrition(calories=calories),
        source=RecipeSource.SYNTHESIZED,
    )


def _cmd(**kwargs: object) -> RecommendationCommand:
    return RecommendationCommand(context=RecommendationContext.MEAL_PLAN, **kwargs)  # type: ignore[arg-type]


_SET: tuple[EvalCase, ...] = (
    EvalCase(
        "on-target", "on-target", _cmd(calorie_target=400), (_recipe("On Target", calories=400),)
    ),
    EvalCase("double", "double", _cmd(calorie_target=400), (_recipe("Double", calories=800),)),
    EvalCase(
        "leak",
        "leak",
        _cmd(allergies=("peanuts",), calorie_target=400),
        (_recipe("Nutty", calories=400, ingredients=("peanuts",)),),
    ),
    EvalCase(
        "twin",
        "twin",
        _cmd(calorie_target=400),
        (_recipe("Twin A", calories=400), _recipe("Twin B", calories=600)),
    ),
)


def test_empty_report_has_zeroed_metrics() -> None:
    report = EvalReport(generated_at="2026-01-01T00:00:00+00:00", cases=())

    assert report.total_recipes == 0
    assert report.constraint_respect == 0.0
    assert report.mean_alignment == 0.0
    assert "0 prompts" in report.summary()


def test_to_dict_exposes_headline_metrics_and_a_breakdown() -> None:
    report = EvalHarness(clock=lambda: _FIXED).run(_SET)

    data = report.to_dict()

    assert data["generated_at"] == "2026-06-25T12:00:00+00:00"
    assert data["constraint_respect"] == 0.8
    assert data["constraint_respect_pct"] == 80.0
    assert data["mean_alignment"] == 0.5
    assert data["mean_alignment_pct"] == 50.0
    assert len(data["cases"]) == 4
    leak = next(case for case in data["cases"] if case["name"] == "leak")
    assert leak["respected"] is False
    assert leak["recipes"][0]["violations"]


def test_summary_reports_both_percentages() -> None:
    summary = EvalHarness(clock=lambda: _FIXED).run(_SET).summary()

    assert "80.0%" in summary
    assert "50.0%" in summary


def test_metrics_is_the_compact_trend_record() -> None:
    report = EvalHarness().run(_SET)

    assert set(report.metrics()) == {
        "generated_at",
        "total_cases",
        "total_recipes",
        "respected_recipes",
        "constraint_respect",
        "mean_alignment",
    }
