"""Test configuration for the commerce service.

The database backend is chosen at import time, in this order:

1. A throwaway Postgres from **Testcontainers** when ``COMMERCE_TEST_DB=postgres`` -- the QA test
   harness (COM-801): a clean, ephemeral Commerce database comes up for the run, no hand-managed
   server required, and is removed when the run ends. ``DB_SOURCE`` becomes ``"testcontainers"``.
   If the container cannot be started (no Docker daemon) the run fails rather than quietly falling
   back, so a mis-wired harness never passes on the wrong database.
2. ``COMMERCE_DATABASE_URL`` when set -- CI points this at a Postgres service container and local
   runs can point it at any database. ``DB_SOURCE`` becomes ``"env"``.
3. A throwaway SQLite file otherwise (no Docker, e.g. a quick in-image run). ``DB_SOURCE`` becomes
   ``"sqlite"``.

The schema is created and dropped around every test for isolation (see ``tests/seed.py`` for the
seed and teardown helpers), and ``seeded_orders`` / ``seeded_payment_methods`` store ready-made data
for :data:`tests.seed.SEED_USER_ID`.
"""

import atexit
import os
import tempfile
import uuid

_requested = os.environ.get("COMMERCE_TEST_DB", "").strip().lower()
_use_testcontainers = _requested in {"postgres", "testcontainers"}


def _start_postgres_container() -> str:
    """Start an ephemeral Postgres via Testcontainers and return its SQLAlchemy URL."""
    from testcontainers.community.postgres import PostgresContainer

    container = PostgresContainer("postgres:16-alpine")
    try:
        container.start()
    except Exception as exc:  # any failure to start means the harness is unusable
        raise RuntimeError(
            "COMMERCE_TEST_DB=postgres asks for an ephemeral Postgres, but Testcontainers could "
            "not start one (is a Docker daemon running?)"
        ) from exc
    atexit.register(container.stop)
    host = container.get_container_host_ip()
    port = container.get_exposed_port(5432)
    return (
        f"postgresql+psycopg://{container.username}:{container.password}"
        f"@{host}:{port}/{container.dbname}"
    )


if _use_testcontainers:
    _DB_URL = _start_postgres_container()
    _DB_SOURCE = "testcontainers"
elif os.environ.get("COMMERCE_DATABASE_URL"):
    _DB_URL = os.environ["COMMERCE_DATABASE_URL"]
    _DB_SOURCE = "env"
else:
    _DB_URL = (
        f"sqlite+pysqlite:///{tempfile.gettempdir()}/commerce_test_{uuid.uuid4().hex}.sqlite3"
    )
    _DB_SOURCE = "sqlite"

# Must be set before importing application modules (settings are read at import time).
os.environ["COMMERCE_DATABASE_URL"] = _DB_URL

DB_SOURCE = _DB_SOURCE
DB_BACKEND = "postgres" if _DB_URL.startswith(("postgres", "postgresql")) else "sqlite"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db import models  # noqa: E402,F401  (register tables on Base.metadata)
from app.db.base import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.repositories.sql_order_repository import SqlOrderRepository  # noqa: E402
from tests.seed import create_schema, drop_schema, seed_orders, seed_payment_methods  # noqa: E402

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


@pytest.fixture(autouse=True)
def _schema():
    create_schema(_engine)
    yield
    drop_schema(_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def engine():
    return _engine


@pytest.fixture
def db_session():
    session = _TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def order_repo(db_session):
    return SqlOrderRepository(db_session)


@pytest.fixture
def seeded_orders(db_session):
    """A pending dark-kitchen order and a confirmed grocery order for ``SEED_USER_ID``."""
    return seed_orders(db_session)


@pytest.fixture
def seeded_payment_methods(db_session):
    """A saved Visa card and a PayPal wallet for ``SEED_USER_ID``."""
    return seed_payment_methods(db_session)


@pytest.fixture(scope="session")
def db_backend() -> str:
    """``"postgres"`` or ``"sqlite"`` -- the backend the suite is running against."""
    return DB_BACKEND


@pytest.fixture(scope="session")
def db_source() -> str:
    """Where the database came from: ``"testcontainers"``, ``"env"`` or ``"sqlite"``."""
    return DB_SOURCE
