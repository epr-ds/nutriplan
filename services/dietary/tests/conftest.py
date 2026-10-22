"""Test configuration for the Dietary service.

The model / repository / schema-validation tests need a real MongoDB (there is no embedded
equivalent for ``$jsonSchema`` validation and indexes). Where it comes from, in order:

1. An ephemeral MongoDB started by **Testcontainers** when ``DIETARY_TEST_DB=mongo`` (DPL-701, the
   QA harness): a throwaway server comes up for the run and goes away after it, no hand-managed
   database needed. ``DB_SOURCE`` becomes ``"testcontainers"``.
2. ``DIETARY_MONGO_URL`` from the environment (CI's service container, the compose
   ``dietary-test`` runner). ``DB_SOURCE`` becomes ``"env"``.
3. ``mongodb://localhost:27017`` otherwise. ``DB_SOURCE`` becomes ``"default"``.

Each run uses a throwaway database name, and any test requesting the ``mongo_db`` fixture is
**skipped** with a clear message when no server is reachable — so a bare in-image run still passes
the Mongo-free tests (health). The ``seeded_recipes`` / ``seeded_plan`` fixtures (built by
``tests/seed.py``) give every Mongo-backed test the same plans and recipes.
"""

import atexit
import os
import time
import uuid

_requested = os.environ.get("DIETARY_TEST_DB", "").lower()


def _start_mongo_container() -> str:
    """Start an ephemeral MongoDB via Testcontainers and return its connection URL."""
    from testcontainers.mongodb import MongoDbContainer

    container = MongoDbContainer("mongo:7")
    container.start()
    atexit.register(container.stop)
    return container.get_connection_url()


if _requested in {"mongo", "testcontainers"}:
    # Must be set before importing application modules (settings are read at import time).
    os.environ["DIETARY_MONGO_URL"] = _start_mongo_container()
    DB_SOURCE = "testcontainers"
else:
    DB_SOURCE = "env" if os.environ.get("DIETARY_MONGO_URL") else "default"

os.environ.setdefault("DIETARY_MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DIETARY_MONGO_DB", f"dietary_test_{uuid.uuid4().hex}")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from pymongo.errors import PyMongoError  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.mongo import (  # noqa: E402
    ensure_favorites_collection,
    ensure_meal_plans_collection,
    ensure_recipes_collection,
)
from app.main import app  # noqa: E402
from tests.seed import seed_catalog, seed_plan  # noqa: E402


def _ping(timeout_ms: int = 1500) -> PyMongoError | None:
    """Ping the server; return the failure, or ``None`` when it answered."""
    client = MongoClient(settings.mongo_url, serverSelectionTimeoutMS=timeout_ms)
    try:
        client.admin.command("ping")
        return None
    except PyMongoError as exc:
        return exc
    finally:
        client.close()


def _wait_for_mongo(attempts: int = 30, timeout_ms: int = 2000) -> PyMongoError | None:
    """Ping until the server answers. The official image starts mongod once to create the root
    user and then restarts it, so a container reported as started may not accept connections
    for a few seconds yet."""
    error = _ping(timeout_ms)
    for _ in range(attempts - 1):
        if error is None:
            break
        time.sleep(1)
        error = _ping(timeout_ms)
    return error


if DB_SOURCE == "testcontainers":
    _error = _wait_for_mongo()
    if _error is not None:
        # The harness was asked for explicitly: a container that cannot be reached is a failure,
        # not a reason to skip every Mongo-backed test.
        raise RuntimeError(f"The Testcontainers MongoDB is not reachable: {_error}")
    _MONGO_UP = True
else:
    _MONGO_UP = _ping() is None


@pytest.fixture
def db_source() -> str:
    """Where the database came from: ``"testcontainers"``, ``"env"`` or ``"default"``."""
    return DB_SOURCE


@pytest.fixture
def client() -> TestClient:
    # Not used as a context manager, so the lifespan (which needs Mongo) does not run.
    return TestClient(app)


@pytest.fixture
def mongo_db():
    """A clean throwaway database with meal_plans set up; dropped afterwards.

    Skips the requesting test when MongoDB is not reachable.
    """
    if not _MONGO_UP:
        pytest.skip("MongoDB not reachable at DIETARY_MONGO_URL")
    client = MongoClient(settings.mongo_url, serverSelectionTimeoutMS=1500)
    client.drop_database(settings.mongo_db)
    db = client[settings.mongo_db]
    ensure_meal_plans_collection(db)
    ensure_recipes_collection(db)
    ensure_favorites_collection(db)
    try:
        yield db
    finally:
        client.drop_database(settings.mongo_db)
        client.close()


@pytest.fixture
def seeded_recipes(mongo_db):
    """The reference recipe catalog, loaded into ``mongo_db`` (DPL-701 fixtures)."""
    return seed_catalog(mongo_db)


@pytest.fixture
def seeded_plan(mongo_db, seeded_recipes):
    """A one-week draft plan with three meals for ``tests.seed.SEED_USER_ID``, stored in
    ``mongo_db`` (DPL-701 fixtures)."""
    return seed_plan(mongo_db, seeded_recipes)
