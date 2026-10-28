"""CI pipeline tests for the Identity service (IDN-801).

The Identity service acceptance criteria require the Backend CI ``identity-service`` job to
build the Docker image (``{target}`` contexts: ``runtime`` / ``test``) in addition to running
lint + tests, and to gate the build before the suite runs.

The workflow file is located via the ``IDENTITY_BACKEND_WORKFLOW`` env var when set
(exact path), else by walking up from this module to the repo root. Under CI the
walk-up always lands on the checkout; locally the env var pins the path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml


def _workflow_path() -> Path | None:
    if override := os.getenv("IDENTITY_BACKEND_WORKFLOW"):
        candidate = Path(override)
        if candidate.is_file():
            return candidate
    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / ".github" / "workflows" / "backend.yml"
        if candidate.is_file():
            return candidate
    return None


_WORKFLOW_PATH = _workflow_path()

if _WORKFLOW_PATH is None:
    # In CI the workflow file is always part of the checkout; a miss means the gate is mis-wired.
    if os.getenv("CI"):
        raise RuntimeError("Backend CI workflow .github/workflows/backend.yml not found in CI.")
    pytest.skip(
        "backend.yml not found; set IDENTITY_BACKEND_WORKFLOW to the workflow path",
        allow_module_level=True,
    )


def _workflow() -> dict[str, Any]:
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))
    return workflow or {}


def _run_steps(job: dict[str, Any]) -> list[str]:
    return [str(step.get("run") or "") for step in job.get("steps") or []]


def test_identity_service_ci_job_exists() -> None:
    jobs = _workflow().get("jobs") or {}
    assert "identity-service" in jobs


def test_identity_service_ci_builds_docker_image_before_tests() -> None:
    """IDN-801: the Identity CI must build the runtime image before the suite runs."""
    job = _workflow()["jobs"]["identity-service"]
    run_steps = _run_steps(job)
    build_indexes = [i for i, run in enumerate(run_steps) if "docker build" in run]
    test_indexes = [i for i, run in enumerate(run_steps) if "pytest" in run]
    assert build_indexes, "identity-service CI must build the Docker image"
    assert test_indexes, "identity-service CI must run the test suite"
    assert min(build_indexes) < min(test_indexes), (
        "identity-service CI must build the Docker image before running tests"
    )