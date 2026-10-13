"""Test configuration for the commerce service.

Tests run against the database in ``COMMERCE_DATABASE_URL``. In CI that points at a Postgres
service container; when unset (e.g. a quick in-image run) it defaults to a throwaway SQLite file.
The schema is created with ``Base.metadata.create_all`` and reset around every test for isolation.
"""

import os
import tempfile
import uuid

# Must be set before importing application modules (settings are read at import time).
os.environ.setdefault(
    "COMMERCE_DATABASE_URL",
    f"sqlite+pysqlite:///{tempfile.gettempdir()}/commerce_test_{uuid.uuid4().hex}.sqlite3",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db import models  # noqa: E402,F401  (register tables on Base.metadata)
from app.db.base import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.repositories.sql_order_repository import SqlOrderRepository  # noqa: E402

_DB_URL = os.environ["COMMERCE_DATABASE_URL"]
_connect_args = {"check_same_thread": False} if _DB_URL.startswith("sqlite") else {}
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
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


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
