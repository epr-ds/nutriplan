"""Idempotent per-boot provisioning for the Commerce database (COM-903).

Single boot-time provisioning entry point for the Commerce databases (COM-903): safe to call
on every boot and versioned through Alembic's migration tracking, so a deploy applies the
schema exactly once per version and stays idempotent.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command
from app.core.config import settings


def provision_commerce(database_url: str | None = None) -> None:
    """Idempotently apply the Commerce schema migrations (``alembic upgrade head``).

    ``database_url`` defaults to the configured Commerce database (environment-driven);
    ``None`` resolves through the service settings.
    """
    app_root = Path(__file__).resolve().parents[2]
    config = Config(str(app_root / "alembic.ini"))
    config.set_main_option("script_location", str(app_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url or str(settings.database_url))
    command.upgrade(config, "head")
