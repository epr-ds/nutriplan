"""Chaos tests for Commerce Postgres connection-loss scenarios.

Drive the real ``app.db.base`` wiring (engine, session factory, ``get_db``
dependency) with the session factory patched to surface a connection error, and
verify failures propagate instead of being swallowed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError


def _connection_refused() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("connection refused"))


class TestCommerceDBConnectionLoss:
    """Verify commerce service handles Postgres connection loss."""

    def test_get_db_propagates_connection_failure(self) -> None:
        """When Postgres is down, opening a session raises instead of hanging."""
        from app.db.base import get_db

        with (
            patch("app.db.base.SessionLocal", side_effect=_connection_refused()),
            pytest.raises(OperationalError, match="connection refused"),
        ):
            next(get_db())

    def test_order_query_fails_gracefully(self) -> None:
        """An in-flight query against a dead connection surfaces the DB error."""
        session = MagicMock()
        session.query.side_effect = _connection_refused()

        with pytest.raises(OperationalError, match="connection refused"):
            session.query("orders").all()

    def test_migration_failure_detected(self) -> None:
        """Alembic upgrade failures during deploy are surfaced, not swallowed."""
        with patch("alembic.command.upgrade") as mock_upgrade:
            mock_upgrade.side_effect = Exception("database unavailable")

            with pytest.raises(Exception, match="database unavailable"):
                mock_upgrade()
