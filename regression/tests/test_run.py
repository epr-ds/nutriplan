"""Regression Suite Runner -- release-gate coverage (HRD-905 / HRD-906).

The runner (``regression/run.py``) is the release gate: it loads each service's regression
corpus and drives the per-case verifiers, then reports and blocks release on P0/P1 failures.

Automated bug-bash finding (HRD-905, task-2): the runner loaded **zero** cases for every
service (``python regression/run.py --services dietary`` reported ``Total: 0``) because no
``services/<service>/regression/corpus.json`` corpus files exist. A release gate that runs
nothing is not a gate.
"""

import pytest

from regression.run import (
    _import_verifier,
    load_regression_corpus,
    run_regression_for_service,
)

DOCUMENTED_SERVICES = ["ai", "commerce", "identity", "dietary", "notification"]


@pytest.mark.parametrize("service", DOCUMENTED_SERVICES)
def test_every_documented_service_loads_a_regression_corpus(service: str) -> None:
    """Each service shipped in the regression suite must load at least one regression case."""
    cases = load_regression_corpus(service)

    assert cases, (
        f"no regression corpus loaded for service {service!r} -- the release gate would run 0 cases"
    )


def test_import_verifier_raises_for_unknown_service() -> None:
    """The runner cannot resolve a verifier for an unknown service and must say so."""
    with pytest.raises(ImportError):
        _import_verifier("no-such-service")


def test_corpus_case_without_verifier_fails_instead_of_faking_pass() -> None:
    """A corpus case whose service has no verifier must not be silently reported as passed."""
    cases = run_regression_for_service("commerce")

    assert cases, "expected the commerce regression corpus to load"
    assert all(not case.passed for case in cases)
