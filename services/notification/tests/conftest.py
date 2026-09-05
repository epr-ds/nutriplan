"""Shared fixtures for the notification suite.

The service is configured entirely through ``NOTIFICATION_``-prefixed environment
variables, which means an ambient value (compose sets ``NOTIFICATION_ENVIRONMENT=test``,
a developer may have a shell export) would otherwise silently change what the tests
observe. Every test builds its own :class:`Settings`, so the ambient values are stripped
first and the suite asserts on the code's real defaults in every environment.

``NOTIFICATION_TEST_REDIS_URL`` is deliberately preserved: it is a *harness* variable
that points the probe suite at a live server, not service configuration.
"""

import os

import pytest

PRESERVED = {"NOTIFICATION_TEST_REDIS_URL"}


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove ambient service configuration so each test controls its own settings."""
    for name in list(os.environ):
        if name.startswith("NOTIFICATION_") and name not in PRESERVED:
            monkeypatch.delenv(name, raising=False)
