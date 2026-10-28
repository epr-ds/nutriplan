"""COM-903: the per-boot provisioning entry point applies the Commerce migrations."""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.db.provisioning import provision_commerce
from tests.seed import drop_schema

_CORE_TABLES = ("addresses", "orders", "order_items")


def test_provision_commerce_applies_the_commerce_migrations(engine: Engine) -> None:
    """COM-903: provisioning applies the Commerce schema migrations for the configured DB."""
    drop_schema(engine)
    provision_commerce(str(settings.database_url))

    inspector = inspect(engine)
    for table in _CORE_TABLES:
        assert inspector.has_table(table)


def test_provision_commerce_is_idempotent(engine: Engine) -> None:
    """COM-903: provisioning is safe to run on every boot (migrations versioned at head)."""
    drop_schema(engine)
    provision_commerce(str(settings.database_url))
    provision_commerce(str(settings.database_url))