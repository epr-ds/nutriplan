"""Test configuration.

The database backend is chosen at import time, in this order:

1. ``IDENTITY_DATABASE_URL`` when set — CI points this at a Postgres service container and
   local runs can point it at any database. ``DB_SOURCE`` becomes ``"env"``.
2. A throwaway Postgres from **Testcontainers** when ``IDENTITY_TEST_DB=postgres`` — this is the
   QA test harness: an ephemeral Identity env comes up on demand, no hand-managed server
   required. ``DB_SOURCE`` becomes ``"testcontainers"``.
3. A throwaway SQLite file otherwise (no Docker, e.g. an in-image run). ``DB_SOURCE`` becomes
   ``"sqlite"``.

Set ``IDENTITY_TEST_DB=sqlite`` to force SQLite even when ``IDENTITY_DATABASE_URL`` is set.

The schema is created with ``Base.metadata.create_all`` and reset around every test for
isolation. The module also seeds fixtures for test accounts (see ``test_account`` /
``auth_headers``).
"""

import atexit
import os
import tempfile
import uuid

# Rate limiting is exercised by a dedicated test; keep it off elsewhere so the
# multi-request flows (e.g. lockout) aren't throttled.
os.environ.setdefault("IDENTITY_RATE_LIMIT_ENABLED", "false")

_requested = os.environ.get("IDENTITY_TEST_DB", "").strip().lower()
_use_testcontainers = _requested in {"postgres", "testcontainers"}


def _start_postgres_container() -> str:
    """Start an ephemeral Postgres via Testcontainers and return its SQLAlchemy URL."""
    from testcontainers.community.postgres import PostgresContainer

    container = PostgresContainer("postgres:16-alpine")
    container.start()
    atexit.register(container.stop)
    host = container.get_container_host_ip()
    port = container.get_exposed_port(5432)
    return (
        f"postgresql+psycopg://{container.username}:{container.password}"
        f"@{host}:{port}/{container.dbname}"
    )


if _use_testcontainers and _requested != "sqlite":
    _DB_URL = _start_postgres_container()
    _DB_SOURCE = "testcontainers"
else:
    _DB_URL = os.environ.get("IDENTITY_DATABASE_URL")
    _DB_SOURCE = "env" if _DB_URL else "sqlite"

if not _DB_URL:
    _DB_URL = f"sqlite+pysqlite:///{tempfile.gettempdir()}/identity_test_{uuid.uuid4().hex}.sqlite3"

# Must be set before importing application modules (settings are read at import time).
os.environ.setdefault("IDENTITY_DATABASE_URL", _DB_URL)

DB_SOURCE = _DB_SOURCE
DB_BACKEND = "postgres" if _DB_URL.startswith(("postgres", "postgresql")) else "sqlite"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db import models  # noqa: E402,F401  (register tables on Base.metadata)
from app.db.base import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

_connect_args = {"check_same_thread": False} if DB_BACKEND == "sqlite" else {}
_engine = create_engine(_DB_URL, connect_args=_connect_args, future=True)
_TestingSessionLocal = sessionmaker(
    bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def _override_get_db():
    db = _TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


# Credentials for the shared test account seeded by the ``test_account`` fixture.
TEST_ACCOUNT_EMAIL = "harness.user@example.com"
TEST_ACCOUNT_PASSWORD = "Harness-Passw0rd!"


@pytest.fixture(autouse=True)
def _schema():
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session():
    """A session bound to the test engine for asserting on persisted rows."""
    session = _TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_account(client) -> dict:
    """A ready-to-use account: register once and hand back its credentials and tokens.

    Tests that need an authenticated user no longer have to re-implement registration;
    they get a seeded account with a valid access/refresh token pair.
    """
    response = client.post(
        "/auth/register",
        json={
            "email": TEST_ACCOUNT_EMAIL,
            "password": TEST_ACCOUNT_PASSWORD,
            "name": "Harness User",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {
        "email": TEST_ACCOUNT_EMAIL,
        "password": TEST_ACCOUNT_PASSWORD,
        "access_token": body["accessToken"],
        "refresh_token": body["refreshToken"],
        "user": body["user"],
    }


@pytest.fixture
def auth_headers(test_account) -> dict:
    """Authorization header for the seeded ``test_account``."""
    return {"Authorization": f"Bearer {test_account['access_token']}"}


@pytest.fixture(scope="session")
def db_backend() -> str:
    """``"postgres"`` or ``"sqlite"`` — the backend the suite is running against."""
    return DB_BACKEND


@pytest.fixture(scope="session")
def db_source() -> str:
    """Where the database came from: ``"env"``, ``"testcontainers"`` or ``"sqlite"``."""
    return DB_SOURCE
