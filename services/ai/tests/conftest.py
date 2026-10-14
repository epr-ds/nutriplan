"""Shared test fixtures for the AI service."""

from __future__ import annotations

import os
from unittest.mock import patch

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
