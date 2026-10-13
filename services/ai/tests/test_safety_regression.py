"""The golden no-allergen regression set, asserted every run (AIA-704).

These tests are the release gate's payload: they pin the shape of
:data:`~app.regression.corpus.GOLDEN_SAFETY_CASES` and run the whole corpus through the production
:class:`~app.recommendations.safety.AllergenFilter`, requiring **zero** surviving allergen /
exclusion violations. They carry the ``regression`` marker so the dedicated CI job can run just
this guarantee; they also run inside the normal suite. A regression -- a leaked allergen or
a lost family expansion -- fails here and blocks the change.
"""

from __future__ import annotations

import pytest

from app.regression.corpus import GOLDEN_SAFETY_CASES
from app.regression.verifier import SafetyRegressionVerifier

pytestmark = pytest.mark.regression


def test_corpus_is_a_nontrivial_golden_set() -> None:
    assert len(GOLDEN_SAFETY_CASES) == 13
    total_recipes = sum(len(case.recipes) for case in GOLDEN_SAFETY_CASES)
    assert total_recipes == 28
    total_unsafe = sum(len(case.expected_unsafe_ids) for case in GOLDEN_SAFETY_CASES)
    assert total_unsafe == 14


def test_case_names_are_unique() -> None:
    names = [case.name for case in GOLDEN_SAFETY_CASES]
    assert len(names) == len(set(names))


def test_corpus_covers_the_major_allergen_families_and_an_exclusion() -> None:
    terms = {
        term.casefold()
        for case in GOLDEN_SAFETY_CASES
        for term in (*case.allergies, *case.excluded)
    }
    for required in (
        "peanuts",
        "shellfish",
        "tree nuts",
        "dairy",
        "eggs",
        "soy",
        "gluten",
        "fish",
        "sesame",
    ):
        assert required in terms, f"corpus does not exercise {required!r}"
    assert any(case.excluded and not case.allergies for case in GOLDEN_SAFETY_CASES)
    assert any(not case.expected_unsafe_ids for case in GOLDEN_SAFETY_CASES)


def test_every_golden_case_holds_the_no_allergen_guarantee() -> None:
    report = SafetyRegressionVerifier().verify(GOLDEN_SAFETY_CASES)

    assert report.ok, f"safety regression detected: {report.failures}"
    assert report.failures == ()


def test_every_unsafe_recipe_is_actually_removed() -> None:
    report = SafetyRegressionVerifier().verify(GOLDEN_SAFETY_CASES)

    for outcome, case in zip(report.outcomes, GOLDEN_SAFETY_CASES, strict=True):
        for unsafe_id in case.expected_unsafe_ids:
            assert unsafe_id not in outcome.kept_ids
        for safe_id in case.expected_safe_ids:
            assert safe_id in outcome.kept_ids
