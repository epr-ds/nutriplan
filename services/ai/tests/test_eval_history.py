"""Unit tests for eval-history trending (AIA-701).

Each run's metrics are appended to a JSONL history, and a run can be compared to the previous one.
These tests cover the round-trip (record then read the latest), the no-history case, the delta math
against a known prior line, and parent-directory creation.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.eval.case import EvalCase
from app.eval.harness import EvalHarness
from app.eval.history import compare_to_previous, latest, record
from app.recommendations.commands import RecommendationCommand, RecommendationContext
from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)


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


# constraint_respect 0.8, mean_alignment 0.5 (see test_eval_harness for the arithmetic).
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


def test_record_appends_and_latest_reads_back(tmp_path: Path) -> None:
    report = EvalHarness().run(_SET)
    path = tmp_path / "history.jsonl"

    record(report, path)
    record(report, path)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert latest(path)["constraint_respect"] == report.constraint_respect


def test_compare_returns_none_without_history(tmp_path: Path) -> None:
    report = EvalHarness().run(_SET)

    assert compare_to_previous(report, tmp_path / "missing.jsonl") is None


def test_compare_computes_deltas_against_the_previous_run(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    previous = {
        "generated_at": "2025-01-01T00:00:00+00:00",
        "constraint_respect": 0.5,
        "mean_alignment": 0.4,
    }
    path.write_text(json.dumps(previous) + "\n", encoding="utf-8")
    report = EvalHarness().run(_SET)

    trend = compare_to_previous(report, path)

    assert trend is not None
    assert trend.previous_at == "2025-01-01T00:00:00+00:00"
    assert trend.delta_constraint_respect == 0.3
    assert trend.delta_mean_alignment == 0.1
    assert "+0.3000" in trend.describe()


def test_record_creates_missing_parent_directories(tmp_path: Path) -> None:
    report = EvalHarness().run(_SET)
    path = tmp_path / "nested" / "dir" / "history.jsonl"

    record(report, path)

    assert path.exists()
