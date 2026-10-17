"""Shared test fixtures for the AI service."""

from __future__ import annotations

import os
import pytest

# Ensure deterministic settings before any app module is imported.
os.environ.setdefault("AI_LLM_PROVIDER", "fake")
os.environ.setdefault("AI_OPENAI_API_KEY", "test-key")


class _FakeTokenVerifier:
    """Returns a deterministic Principal for any token — no JWKS needed."""

    def verify(self, token: str) -> object:  # type: ignore[no-untyped-def]
        from app.core.principal import Principal

        return Principal(user_id="contract-test-user", email="test@nutriplan.local")


def _fake_token_verifier() -> _FakeTokenVerifier:
    """Factory for the fake token verifier."""
    return _FakeTokenVerifier()


# ── Global JWT patch (applied at import time, before any TestClient is created) ──
# Many test files create `client = TestClient(app)` at module level, so fixture-based
# dependency overrides won't help. We patch app.dependency_overrides directly here.

from app.api.deps import get_token_verifier  # noqa: E402
from app.main import app  # noqa: E402


class _GlobalFakeVerifier:
    """Global fake verifier that works for all tests."""

    def verify(self, token: str) -> object:  # type: ignore[no-untyped-def]
        from app.core.principal import Principal

        return Principal(user_id="test-user", email="test@nutriplan.local")


# Apply override at import time — before any test module creates its TestClient.
app.dependency_overrides[get_token_verifier] = lambda: _GlobalFakeVerifier()  # type: ignore[assignment]


@pytest.fixture(autouse=True, scope="function")
def _reapply_token_verifier() -> None:
    """Re-apply the global token verifier override.

    The contract tests fixture calls `app.dependency_overrides.clear()` in a finally block.
    We use yield to ensure the override is re-applied after each test runs.
    """
    app.dependency_overrides[get_token_verifier] = lambda: _GlobalFakeVerifier()  # type: ignore[assignment]
    try:
        yield
    finally:
        app.dependency_overrides[get_token_verifier] = lambda: _GlobalFakeVerifier()  # type: ignore[assignment]

