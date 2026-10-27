"""CI pipeline tests for the Dietary service (DPL-801).

The Dietary service acceptance criteria require the Backend CI ``dietary-service`` job to
build the Docker image (``{target}`` contexts: ``runtime`` / ``test``) in addition to running
lint + tests.

The workflow file is located via the ``DIETARY_BACKEND_WORKFLOW`` env var when set
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
    if override := os.getenv("DIETARY_BACKEND_WORKFLOW"):
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
        "backend.yml not found; set DIETARY_BACKEND_WORKFLOW to the workflow path",
        allow_module_level=True,
    )


def _workflow() -> dict[str, Any]:
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))
    return workflow or {}


def test_dietary_service_ci_job_exists() -> None:
    jobs = _workflow().get("jobs") or {}
    assert "dietary-service" in jobs


def test_dietary_service_ci_builds_docker_image() -> None:
    job = _workflow()["jobs"]["dietary-service"]
    steps = job.get("steps") or []
    run_steps = [str(step.get("run") or "") for step in steps]
    assert any("docker build" in run for run in run_steps)