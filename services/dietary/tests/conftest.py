"""Test configuration for the Dietary service.

The model / repository / schema-validation tests need a real MongoDB (there is no embedded
equivalent for ``$jsonSchema`` validation and indexes). They connect to ``DIETARY_MONGO_URL``
using a throwaway database, and any test requesting the ``mongo_db`` fixture is **skipped** with
a clear message when no server is reachable — so a bare in-image run still passes the Mongo-free
tests (health). In CI and the compose ``dietary-test`` runner a Mongo service is always present.
"""

import os
import uuid

# Must be set before importing application modules (settings are read at import time).
os.environ.setdefault("DIETARY_MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DIETARY_MONGO_DB", f"dietary_test_{uuid.uuid4().hex}")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from pymongo.errors import PyMongoError  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.mongo import ensure_meal_plans_collection, ensure_recipes_collection  # noqa: E402
from app.main import app  # noqa: E402


def _mongo_available() -> bool:
    try:
        client = MongoClient(settings.mongo_url, serverSelectionTimeoutMS=1500)
        client.admin.command("ping")
        client.close()
        return True
    except PyMongoError:
        return False


_MONGO_UP = _mongo_available()


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
    try:
        yield db
    finally:
        client.drop_database(settings.mongo_db)
        client.close()
