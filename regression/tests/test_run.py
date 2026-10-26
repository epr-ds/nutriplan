"""Regression Suite Runner -- release-gate coverage (HRD-905 / HRD-906).

The runner (``regression/run.py``) is the release gate: it loads each service's regression
corpus, drives the per-case verifiers and reports / blocks release on P0/P1 failures.

The gate is only meaningful if it can actually execute the regression cases it loads; a gate
that reports spurious failures over an un-executable corpus is not a gate, and it cannot
substantiate the GA release sign-off exit criteria (HRD-805 / HRD-906).
"""

from regression.run import run_regression_for_service


def test_ai_golden_corpus_passes_the_release_gate() -> None:
    """The release gate must be able to execute the AI golden corpus and pass on the green set.

    Driving the runner over the AI regression must not fail merely because of an invocation
    mismatch between the corpus case and the verifier; on a green corpus the gate must pass.
    """
    results = run_regression_for_service("ai")

    assert results, "expected the AI regression corpus to load"
    assert all(result.passed for result in results)
