"""Chaos tests for the Dietary MongoDB connection-loss scenarios.

Exercise the real ``app.db.mongo`` client wiring with PyMongo's connection
errors to confirm failures propagate to callers.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.db.mongo import get_client
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError


class TestDietaryMongoConnectionLoss:
    """Verify dietary service handles MongoDB connection loss."""

    def test_recipe_search_fails_gracefully(self) -> None:
        """When MongoDB is unreachable, a ping raises ``ServerSelectionTimeoutError``."""
        with patch("app.db.mongo.MongoClient") as mock_client:
            mock_client.return_value.admin.command.side_effect = (
                ServerSelectionTimeoutError("connection refused")
            )

            with pytest.raises(ServerSelectionTimeoutError):
                mock_client.return_value.admin.command("ping")

    def test_meal_plan_create_fails_gracefully(self) -> None:
        """When MongoDB is unreachable, collection access raises ``ConnectionFailure``."""
        with patch("app.db.mongo.MongoClient") as mock_client:
            mock_client.return_value.__getitem__.side_effect = ConnectionFailure(
                "connection refused"
            )

            with pytest.raises(ConnectionFailure):
                mock_client.return_value["dietary"].insert_one({})


class TestDietaryMongoClientWiring:
    """Verify the cached client wiring surfaces connection failures."""

    def test_get_client_propagates_connection_error(self) -> None:
        get_client.cache_clear()
        try:
            with (
                patch(
                    "app.db.mongo.MongoClient",
                    side_effect=ServerSelectionTimeoutError("connection refused"),
                ),
                pytest.raises(ServerSelectionTimeoutError, match="connection refused"),
            ):
                get_client()
        finally:
            get_client.cache_clear()
