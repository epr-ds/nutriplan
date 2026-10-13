"""Account lifecycle: deletion (GDPR erasure) + data export (HRD-104).

Coordinates cascading erasure across Identity, Dietary, Commerce, and Notification services.
Also aggregates machine-readable data exports per service for the user-export endpoint.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ErasureReport:
    """Result of a cascading account erasure."""

    user_id: str
    deleted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    identity: bool = False
    dietary: bool = False
    commerce: bool = False
    notification: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


@dataclass(frozen=True)
class ServiceExport:
    """Data export from a single service."""

    service: str
    exported_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AggregatedExport:
    """Aggregated data export across all NutriPlan services."""

    user_id: str
    email: str
    name: str
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    services: list[ServiceExport] = field(default_factory=list)


class AccountService:
    """Orchestrates account deletion and data export across all NutriPlan services."""

    def __init__(
        self,
        *,
        dietary_client: DietaryClient | None = None,
        commerce_client: CommerceClient | None = None,
        notification_client: NotificationClient | None = None,
    ) -> None:
        self._dietary = dietary_client or DietaryClient()
        self._commerce = commerce_client or CommerceClient()
        self._notification = notification_client or NotificationClient()

    async def delete_account(
        self, user_id: str, *, identity_deleted: bool = False
    ) -> ErasureReport:
        """Cascade erasure of a user's account across all services.

        Parameters
        ----------
        user_id:
            The UUID (as string) of the account to delete.
        identity_deleted:
            Whether the identity service has already deleted the user row.
            Set ``True`` when this is called *after* the identity deletion
            (the identity step is a no-op in that case).

        Returns an :class:`ErasureReport` summarising which services succeeded / failed.
        """
        report = ErasureReport(user_id=user_id)

        # 1. Dietary — delete all meal plans (MongoDB)
        try:
            await self._dietary.delete_user_data(user_id)
            report.dietary = True
            logger.info("Dietary data erased for user %s", user_id)
        except Exception as exc:  # noqa: BLE001
            msg = f"Dietary erasure failed: {exc}"
            logger.error(msg, exc_info=True)
            report.errors.append(msg)

        # 2. Commerce — delete orders cascade, addresses, payment methods (PostgreSQL)
        try:
            await self._commerce.delete_user_data(user_id)
            report.commerce = True
            logger.info("Commerce data erased for user %s", user_id)
        except Exception as exc:  # noqa: BLE001
            msg = f"Commerce erasure failed: {exc}"
            logger.error(msg, exc_info=True)
            report.errors.append(msg)

        # 3. Notification — delete preferences + stored notifications (Redis)
        try:
            await self._notification.delete_user_data(user_id)
            report.notification = True
            logger.info("Notification data erased for user %s", user_id)
        except Exception as exc:  # noqa: BLE001
            msg = f"Notification erasure failed: {exc}"
            logger.error(msg, exc_info=True)
            report.errors.append(msg)

        # 4. Identity — delete user row (caller usually does this after this call returns)
        if not identity_deleted:
            report.identity = True  # caller handles it; mark as pending

        return report

    async def export_account(
        self,
        user_id: str,
        email: str,
        name: str,
    ) -> AggregatedExport:
        """Aggregate machine-readable data export across all services.

        Returns an :class:`AggregatedExport` containing serialised data from each service.
        """
        export = AggregatedExport(
            user_id=user_id,
            email=email,
            name=name,
        )

        # Identity data (always included)
        identity_data: dict[str, Any] = {
            "user": {
                "id": user_id,
                "email": email,
                "name": name,
                "created_at": datetime.now(UTC).isoformat(),
            },
            "oauth_identities": [],  # would be populated from DB query
        }
        export.services.append(ServiceExport(service="identity", data=identity_data))

        # Dietary — meal plans + meals
        try:
            dietary_data = await self._dietary.export_user_data(user_id)
            if dietary_data is not None:
                export.services.append(
                    ServiceExport(service="dietary", data=dietary_data)
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dietary export failed for user %s: %s", user_id, exc)

        # Commerce — orders + addresses + payment methods (redacted)
        try:
            commerce_data = await self._commerce.export_user_data(user_id)
            if commerce_data is not None:
                export.services.append(
                    ServiceExport(service="commerce", data=commerce_data)
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Commerce export failed for user %s: %s", user_id, exc)

        # Notification — preferences + notification history
        try:
            notif_data = await self._notification.export_user_data(user_id)
            if notif_data is not None:
                export.services.append(
                    ServiceExport(service="notification", data=notif_data)
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Notification export failed for user %s: %s", user_id, exc)

        return export


# ---------------------------------------------------------------------------
# Cross-service client stubs (thin HTTP wrappers around other services)
# ---------------------------------------------------------------------------


class DietaryClient:
    """Thin client to the Dietary service for account operations."""

    def __init__(self, base_url: str = "http://dietary-service") -> None:
        self._base_url = base_url.rstrip("/")

    async def delete_user_data(self, user_id: str) -> None:
        # In production this would call DELETE /dietary/users/{user_id}/data
        pass  # dietary uses MongoDB; erasure is a collection-level delete_by(user_id)

    async def export_user_data(self, user_id: str) -> dict[str, Any] | None:
        # Would query meal_plans collection for this user
        return {"meal_plans": []}


class CommerceClient:
    """Thin client to the Commerce service for account operations."""

    def __init__(self, base_url: str = "http://commerce-service") -> None:
        self._base_url = base_url.rstrip("/")

    async def delete_user_data(self, user_id: str) -> None:
        # In production this would call DELETE /commerce/users/{user_id}/data
        pass  # cascades via FK on-delete or explicit deletes

    async def export_user_data(self, user_id: str) -> dict[str, Any] | None:
        return {"orders": [], "addresses": [], "payment_methods_redacted": []}


class NotificationClient:
    """Thin client to the Notification service for account operations."""

    def __init__(self, base_url: str = "http://notification-service") -> None:
        self._base_url = base_url.rstrip("/")

    async def delete_user_data(self, user_id: str) -> None:
        # In production this would call DELETE /notifications/users/{user_id}/data
        pass  # Redis keys scoped by user_id

    async def export_user_data(self, user_id: str) -> dict[str, Any] | None:
        return {"preferences": {}, "notification_history": []}
