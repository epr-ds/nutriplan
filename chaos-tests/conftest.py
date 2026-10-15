"""Shared fixtures for chaos tests.

These tests validate resilience patterns by injecting failures and verifying
graceful degradation. They run against the service code directly (unit/integration)
rather than against live services.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to sys.path so 'services' package is importable
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import time
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Clock helpers
# ---------------------------------------------------------------------------


class FakeClock:
    """Monotonic clock that advances on demand for deterministic chaos tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture()
def fake_clock() -> FakeClock:
    return FakeClock()


# ---------------------------------------------------------------------------
# Failure injectors
# ---------------------------------------------------------------------------


class FailureInjector:
    """Inject failures into code paths for chaos testing."""

    def __init__(self) -> None:
        self._failures: dict[str, int] = {}
        self._call_counts: dict[str, int] = {}

    def inject(self, key: str, count: int = 1) -> None:
        """Make the next ``count`` calls to ``key`` raise."""
        self._failures[key] = count
        self._call_counts[key] = 0

    def should_fail(self, key: str) -> bool:
        """Return True if the next call to ``key`` should fail."""
        self._call_counts[key] = self._call_counts.get(key, 0) + 1
        remaining = self._failures.get(key, 0)
        if remaining > 0 and self._call_counts[key] <= remaining:
            return True
        return False

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
        self._call_counts.pop(key, None)


@pytest.fixture()
def injector() -> FailureInjector:
    return FailureInjector()


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def mock_db_error() -> MagicMock:
    """Create a mock that raises a DB connection error."""
    error = Exception("connection refused")
    error.__class__.__name__ = "OperationalError"
    return error


def mock_redis_error() -> MagicMock:
    """Create a mock that raises a Redis connection error."""
    error = Exception("Connection refused")
    error.__class__.__name__ = "ConnectionError"
    return error


def mock_http_error(status_code: int = 503) -> MagicMock:
    """Create a mock HTTP response with the given status code."""
    response = MagicMock()
    response.status_code = status_code
    response.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return response


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------


@pytest.fixture()
def grocery_providers() -> list[str]:
    return ["chedraui", "walmart", "freshbasket"]


@pytest.fixture()
def valid_order_request() -> dict[str, Any]:
    return {
        "items": [{"sku": "TEST001", "quantity": 2}],
        "delivery_address": {"street": "123 Main St", "city": "CDMX"},
        "delivery_slot": "2024-01-15T10:00:00Z",
    }


@pytest.fixture()
def valid_event() -> dict[str, Any]:
    return {
        "type": "order.created",
        "id": "evt_test_001",
        "data": {"order_id": "ord_123"},
        "timestamp": "2024-01-15T10:00:00Z",
    }


@pytest.fixture()
def llm_request() -> dict[str, Any]:
    return {
        "messages": [
            {"role": "user", "content": "What should I eat for breakfast?"},
        ],
        "model": "gpt-4",
        "max_tokens": 500,
    }
