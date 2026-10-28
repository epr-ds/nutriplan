"""Stage deploy workflow tests for the seeded demo plan + recipes (DPL-806).

The stage deploy is the release gate that runs before the private beta: it deploys the
Dietary runtime to stage, seeds the demo plan + recipes and has to come back green through
the smoke path (health + seeded catalog served).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_LOCAL_CANDIDATES: list[Path] = [
    ancestor / ".github" / "workflows" / "dietary-stage-deploy.yml"
    for ancestor in Path(__file__).resolve().parents
]
_LOCAL_CANDIDATES = [candidate for candidate in _LOCAL_CANDIDATES if candidate.is_file()]


def _workflow_path() -> Path | None:
    if override := os.getenv("DIETARY_STAGE_DEPLOY_WORKFLOW"):
        candidate = Path(override)
        if candidate.is_file():
            return candidate
    for candidate in _LOCAL_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def _workflow() -> dict[str, Any]:
    path = _workflow_path()
    assert path is not None, "Dietary stage deploy workflow not found"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    return workflow or {}


def test_stage_deploy_workflow_seeds_and_smokes() -> None:
    """DPL-806: the stage deploy must seed the demo plan + recipes and pass the smoke check."""
    workflow = _workflow()
    jobs = workflow.get("jobs") or {}
    assert "deploy" in jobs
    steps = jobs["deploy"].get("steps") or []
    joined = "\n".join(f"{step.get('name') or ''}\n{step.get('run') or ''}" for step in steps)
    assert "seed" in joined.lower()
    assert "smoke" in joined.lower()