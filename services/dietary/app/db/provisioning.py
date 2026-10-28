"""Idempotent per-boot provisioning for the Dietary MongoDB (DPL-803)."""

from __future__ import annotations

from pymongo.database import Database

from app.db.mongo import (
    ensure_favorites_collection,
    ensure_meal_plans_collection,
    ensure_recipes_collection,
    recipes,
)
from app.db.seed import seed_recipes


def provision_dietary(db: Database) -> None:
    """Idempotently install the validators + indexes and seed the reference catalog.

    Single boot-time provisioning entry point for the Dietary databases (DPL-803): safe to call
    on every boot, and the source of truth for what the service guarantees before serving
    traffic (indexes from DPL-101/DPL-202/DPL-607, reference catalog from DPL-201).
    """
    ensure_meal_plans_collection(db)
    ensure_recipes_collection(db)
    ensure_favorites_collection(db)
    seed_recipes(recipes(db))
