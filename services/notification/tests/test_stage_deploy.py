"""Stage/deploy workflow tests for the Notification service (NTF-701).

The notification service ships through the pipeline: the deploy job builds the runtime image,
brings the service up on the dev stage through the smoke path (liveness + readiness against a
live Redis) and has to come back green before the deploy is considered shipped.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_LOCAL_CANDIDATES: list[Path] = [
    ancestor / ".github" / "workflows" / "notification-stage-deploy.yml"
    for ancestor in Path(__file__).resolve().parents
]
_LOCAL_CANDIDATES = [candidate for candidate in _LOCAL_CANDIDATES if candidate.is_file()]


def _workflow_path() -> Path | None:
    if override := os.getenv("NOTIFICATION_STAGE_DEPLOY_WORKFLOW"):
        candidate = Path(override)
        if candidate.is_file():
            return candidate
    for candidate in _LOCAL_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def _workflow() -> dict[str, Any]:
    path = _workflow_path()
    assert path is not None, "Notification stage deploy workflow not found"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    return workflow or {}


def test_stage_deploy_workflow_smokes_the_service() -> None:
    """NTF-701: the dev-stage deploy must bring the notification service up and pass smoke."""
    workflow = _workflow()
    jobs = workflow.get("jobs") or {}
    assert "deploy" in jobs
    steps = jobs["deploy"].get("steps") or []
    joined = "\n".join(f"{step.get('name') or ''}\n{step.get('run') or ''}" for step in steps)
    assert "smoke" in joined.lower()
