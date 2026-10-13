"""Schemas for account management (HRD-104: deletion + data export)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import EmailStr, Field

from app.schemas.base import CamelModel


class AccountDeletionConfirm(CamelModel):
    """Payload for confirming account deletion (requires user to type their email)."""

    confirm_email: EmailStr = Field(
        ..., description="User's email — must match the authenticated account."
    )


class AccountExportResponse(CamelModel):
    """Machine-readable data export for a single service."""

    service: str
    exported_at: datetime
    data: dict[str, Any]


class DataExportResponse(CamelModel):
    """Aggregated data export across all NutriPlan services."""

    user_id: uuid.UUID
    email: EmailStr
    name: str
    requested_at: datetime
    services: list[AccountExportResponse]
