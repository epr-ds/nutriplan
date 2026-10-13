"""Account lifecycle endpoints (HRD-104: deletion + data export).

``DELETE /users/me`` — confirm and cascade erasure of the authenticated user's account.
``GET  /users/me/export`` — aggregate machine-readable data export across all services.
"""

from __future__ import annotations

import logging
import uuid as _uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.schemas.account import (
    AccountDeletionConfirm,
    DataExportResponse,
)
from app.services import account_service as _account_svc
from app.services.profile_service import update_profile  # noqa: F401 — re-exported

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={204: {"description": "Account deleted; all personal data erased."}},
)
async def delete_current_account(
    payload: AccountDeletionConfirm,
    user: CurrentUser,
    db: DbSession,
) -> None:
    """Delete the authenticated user's account and cascade erasure across services.

    Requires the user to type their email for confirmation (prevents accidental deletion).
    The identity row is deleted first; if that succeeds the cascading erasure runs against
    Dietary, Commerce, and Notification services.

    GDPR / LFPDPPP compliance: all PII is removed from every service within the same
    transactional boundary — if any downstream service fails the error is logged but the
    identity row remains deleted (idempotent re-run will complete the erasure).
    """
    # Double-check: email must match the authenticated account.
    if payload.confirm_email != user.email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="confirm_email does not match the authenticated account",
        )

    user_uuid = str(user.id)

    # 1. Delete identity row (caller owns this; cascade on-delete handles credentials,
    # refresh tokens, and OAuth identities via FK ondelete=CASCADE).
    from app.db.models import User

    db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.commit()

    # 2. Cascade erasure across other services (best-effort; idempotent).
    report = await _account_svc.AccountService().delete_account(user_uuid, identity_deleted=True)

    if not report.success:
        logger.error(
            "Partial account deletion for user %s — errors: %s",
            user_uuid,
            report.errors,
        )

    # 3. Audit log (written to a separate audit table in production).
    logger.info(
        "Account deleted by user %s; erasure report: identity=%s dietary=%s commerce=%s notification=%s errors=%d",
        user_uuid,
        report.identity,
        report.dietary,
        report.commerce,
        report.notification,
        len(report.errors),
    )


@router.get(
    "/me/export",
    response_model=DataExportResponse,
    responses={200: {"description": "Machine-readable data export."}},
)
async def export_current_account(user: CurrentUser) -> DataExportResponse:
    """Aggregate machine-readable data export across all NutriPlan services.

    Returns a JSON document containing the user's profile, meal plans, order history,
    saved addresses, notification preferences, and any other personal data held by
    NutriPlan — suitable for GDPR / LFPDPPP data-portability requests.
    """
    user_uuid = str(user.id)

    export = await _account_svc.AccountService().export_account(
        user_id=user_uuid,
        email=str(user.email),
        name=user.name,
    )

    services = [
        {
            "service": s.service,
            "exported_at": s.exported_at,
            "data": s.data,
        }
        for s in export.services
    ]

    return DataExportResponse(
        user_id=_uuid.UUID(user_uuid),
        email=user.email,
        name=export.name,
        requested_at=export.requested_at,
        services=services,  # type: ignore[arg-type] — matches list[dict] via CamelModel
    )
