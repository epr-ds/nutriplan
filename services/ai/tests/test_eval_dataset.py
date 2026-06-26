"""Guard tests for the fixed eval set (AIA-701).

The eval set is a version-controlled fixture: these tests pin its shape (coverage of every
constraint type, a deterministic mix of respected and leaking outputs) so an accidental edit that
would silently move the metrics is caught. The exact baseline numbers are asserted on the discrete,
reliable counts; alignment is asserted as a sane band.
"""

from __future__ import annotations

from app.eval.dataset import EVAL_SET
from app.eval.harness import EvalHarness


def test_eval_set_is_non_trivial() -> None:
    assert len(EVAL_SET) >= 6


def test_case_names_are_unique() -> None:
    names = [case.name for case in EVAL_SET]
    assert len(names) == len(set(names))


def test_every_case_has_a_prompt_and_recorded_recipes() -> None:
    for case in EVAL_SET:
        assert case.name
        assert case.prompt
        assert case.recipes


def test_covers_each_known_constraint_type() -> None:
    assert any(case.command.diet_type for case in EVAL_SET)
    assert any(case.command.allergies for case in EVAL_SET)
    assert any(case.command.macro_targets for case in EVAL_SET)
    assert any(case.command.effective_calories() for case in EVAL_SET)


def test_harness_grades_the_whole_set_with_a_stable_baseline() -> None:
    report = EvalHarness().run(EVAL_SET)

    assert report.total_cases == len(EVAL_SET)
    # Exactly two recorded outputs deliberately leak a hard constraint.
    assert report.total_recipes - report.respected_recipes == 2
    assert report.constraint_respect == 0.8667
    assert 0.6 < report.mean_alignment < 0.95


def test_set_contains_both_respected_and_leaking_cases() -> None:
    report = EvalHarness().run(EVAL_SET)

    assert 0 < report.respected_cases < report.total_cases
