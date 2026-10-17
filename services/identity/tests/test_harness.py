"""Tests for the ephemeral Identity test harness itself.

Covers the seeded ``test_account`` fixture and asserts that the Testcontainers Postgres path
actually serves the suite when it is requested (``IDENTITY_TEST_DB=postgres``).
"""

import os

import pytest

from tests.conftest import TEST_ACCOUNT_EMAIL


def test_seeded_account_can_reach_a_protected_endpoint(client, auth_headers):
    response = client.get("/users/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["email"] == TEST_ACCOUNT_EMAIL


def test_seeded_account_refresh_token_is_usable(client, test_account):
    response = client.post("/auth/refresh", json={"refreshToken": test_account["refresh_token"]})

    assert response.status_code == 200
    assert response.json()["accessToken"]


def test_harness_reports_a_known_backend(db_backend, db_source):
    assert db_backend in {"postgres", "sqlite"}
    assert db_source in {"env", "testcontainers", "sqlite"}


@pytest.mark.skipif(
    os.environ.get("IDENTITY_TEST_DB", "").strip().lower() not in {"postgres", "testcontainers"},
    reason="Testcontainers was not requested (IDENTITY_TEST_DB)",
)
def test_suite_runs_on_an_ephemeral_postgres_container(db_backend, db_source):
    assert db_backend == "postgres"
    assert db_source == "testcontainers"
