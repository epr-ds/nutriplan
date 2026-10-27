"""Compose wiring tests for the AI service (AIA-803).

The AI cache/budget Redis backing (AIA-105) is switched per environment through
``AI_REDIS_URL`` (see ``app.kv.factory``). The compose file must therefore give
the AI service a Redis URL in every environment it serves, defaulting to the
compose ``redis`` service and overridable per environment via the same variable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

_LOCAL_CANDIDATES: list[Path] = [
    ancestor / "infra" / "docker-compose.yml"
    for ancestor in Path(__file__).resolve().parents
]
_LOCAL_CANDIDATES = [candidate for candidate in _LOCAL_CANDIDATES if candidate.is_file()]


def _compose_path() -> Path | None:
    if override := os.getenv("AI_COMPOSE_FILE"):
        candidate = Path(override)
        if candidate.is_file():
            return candidate
    for candidate in _LOCAL_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


_COMPOSE_PATH = _compose_path()

if _COMPOSE_PATH is None:
    # In CI the compose file is part of the checkout; a miss means the gate is mis-wired.
    if os.getenv("CI"):
        raise RuntimeError("infra/docker-compose.yml not found in CI.")
    pytest.skip(
        "infra/docker-compose.yml not found; set AI_COMPOSE_FILE to the compose file",
        allow_module_level=True,
    )


def _compose() -> dict[str, Any]:
    compose = yaml.safe_load(_COMPOSE_PATH.read_text(encoding="utf-8"))
    return compose or {}


def test_ai_service_redis_url_configured() -> None:
    services = _compose().get("services") or {}
    ai = services.get("ai") or {}
    env = ai.get("environment") or {}
    assert env.get("AI_REDIS_URL")