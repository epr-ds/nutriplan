"""DPL-607: the Mongo favorites adapter, the collection's schema validation and its indexes.

These need a real MongoDB (``$jsonSchema`` validation and unique indexes have no in-memory
equivalent); the ``mongo_db`` fixture skips them when no server is reachable.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pymongo.errors import DuplicateKeyError, WriteError

from app.db.mongo import FAVORITES
from app.domain.favorite import Favorite
from app.repositories.mongo_favorite_repository import MongoFavoriteRepository


def _favorite(user: str, recipe: str, minutes: int = 0) -> Favorite:
    when = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minutes)
    return Favorite(user_id=user, recipe_id=recipe, created_at=when)


@pytest.fixture
def repo(mongo_db) -> MongoFavoriteRepository:
    return MongoFavoriteRepository(mongo_db[FAVORITES])


def test_add_and_list_roundtrip(repo):
    repo.add(_favorite("u1", "r1"))

    saved = repo.list_for_user("u1")

    assert [(f.user_id, f.recipe_id) for f in saved] == [("u1", "r1")]
    assert saved[0].created_at == datetime(2026, 1, 1, tzinfo=UTC)


def test_adding_the_same_recipe_twice_keeps_one_document_and_its_timestamp(repo, mongo_db):
    repo.add(_favorite("u1", "r1", minutes=0))
    repo.add(_favorite("u1", "r1", minutes=30))

    assert mongo_db[FAVORITES].count_documents({}) == 1
    assert repo.list_for_user("u1")[0].created_at == datetime(2026, 1, 1, tzinfo=UTC)


def test_remove_deletes_only_that_users_favorite(repo):
    repo.add(_favorite("u1", "r1"))
    repo.add(_favorite("u2", "r1"))

    repo.remove("u1", "r1")

    assert repo.list_for_user("u1") == []
    assert [f.recipe_id for f in repo.list_for_user("u2")] == ["r1"]


def test_remove_of_a_missing_favorite_is_a_no_op(repo):
    repo.remove("u1", "never-saved")


def test_list_is_scoped_to_the_user_and_newest_first(repo):
    repo.add(_favorite("u1", "old", minutes=0))
    repo.add(_favorite("u1", "new", minutes=10))
    repo.add(_favorite("u1", "mid", minutes=5))
    repo.add(_favorite("u2", "other", minutes=20))

    assert [f.recipe_id for f in repo.list_for_user("u1")] == ["new", "mid", "old"]


def test_list_skips_and_limits(repo):
    for minutes, recipe in enumerate(["a", "b", "c"]):
        repo.add(_favorite("u1", recipe, minutes=minutes))

    page = repo.list_for_user("u1", skip=1, limit=1)

    assert [f.recipe_id for f in page] == ["b"]


# --- schema validation and indexes ----------------------------------------------------------


def _doc(**overrides) -> dict:
    doc = {
        "_id": "fav-1",
        "userId": "u1",
        "recipeId": "r1",
        "createdAt": "2026-01-01T00:00:00Z",
    }
    doc.update(overrides)
    return doc


def test_a_valid_document_is_accepted(mongo_db):
    assert mongo_db[FAVORITES].insert_one(_doc()).inserted_id == "fav-1"


@pytest.mark.parametrize("missing", ["userId", "recipeId", "createdAt"])
def test_a_missing_required_field_is_rejected(mongo_db, missing):
    doc = _doc()
    del doc[missing]
    with pytest.raises(WriteError):
        mongo_db[FAVORITES].insert_one(doc)


def test_an_empty_recipe_id_is_rejected(mongo_db):
    with pytest.raises(WriteError):
        mongo_db[FAVORITES].insert_one(_doc(recipeId=""))


def test_the_pair_is_unique_per_user(mongo_db):
    mongo_db[FAVORITES].insert_one(_doc())

    with pytest.raises(DuplicateKeyError):
        mongo_db[FAVORITES].insert_one(_doc(_id="fav-2"))


def test_two_users_can_save_the_same_recipe(mongo_db):
    mongo_db[FAVORITES].insert_one(_doc())

    mongo_db[FAVORITES].insert_one(_doc(_id="fav-2", userId="u2"))


def test_the_expected_indexes_exist(mongo_db):
    indexes = {ix["name"]: ix for ix in mongo_db[FAVORITES].list_indexes()}

    assert list(indexes["userId_recipeId"]["key"].keys()) == ["userId", "recipeId"]
    assert indexes["userId_recipeId"].get("unique") is True
    assert list(indexes["userId_createdAt"]["key"].keys()) == ["userId", "createdAt"]
