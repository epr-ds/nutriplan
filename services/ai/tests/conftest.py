"""Shared test fixtures for the AI service."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

# Ensure deterministic settings before any app module is imported.
os.environ.setdefault("AI_LLM_PROVIDER", "fake")
os.environ.setdefault("AI_OPENAI_API_KEY", "test-key")


@pytest.fixture(autouse=True, scope="session")
def _mock_jwks_url():
    """Prevent PyJWKClient from failing on empty JWKS URL in tests.

    The AI service config is a module-level singleton that reads env vars at import time.
    We set ``AI_IDENTITY_JWKS_URL`` here so the Settings instance (created when app.core.config
    is imported) picks up a valid URL instead of the empty default.
    """
    with patch.dict(os.environ, {"AI_IDENTITY_JWKS_URL": "http://localhost/.well-known/jwks.json"}):
        yield

