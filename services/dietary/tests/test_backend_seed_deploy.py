"""Deploy workflow tests for the curated recipe seed (DPL-804).

The curated recipe catalog seeds at service startup through an idempotent upsert
(``app.db.seed.seed_recipes``); the DPL-804 acceptance criterion requires a deploy job
that runs this seed against the target environment on deploy.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_LOCAL_CANDIDATES: list[Path] = [
    ancestor / ".github" / "workflows" / "dietary-seed-deploy.yml"
    for ancestor in Path(__file__).resolve().parents
]
_LOCAL_CANDIDATES = [candidate for candidate in _LOCAL_CANDIDATES if candidate.is_file()]


def _workflow_path() -> Path | None:
    if override := os.getenv("DIETARY_SEED_DEPLOY_WORKFLOW"):
        candidate = Path(override)
        if candidate.is_file():
            return candidate
    for candidate in _LOCAL_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def _workflow() -> dict[str, Any]:
    path = _workflow_path()
    assert path is not None, "Dietary seed deploy workflow not found"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    return workflow or {}


def test_seed_deploy_workflow_seeds_the_catalog() -> None:
    """DPL-804: a deploy workflow runs the idempotent curated seed catalog load."""
    workflow = _workflow()
    jobs = workflow.get("jobs") or {}
    assert "seed" in jobs
    steps = jobs["seed"].get("steps") or []
    joined = "\n".join(f"{step.get('name') or ''}\n{step.get('run') or ''}" for step in steps)
    assert "seed" in joined.lower()