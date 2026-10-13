"""SQLAlchemy adapter implementing the :class:`~app.application.ports.SlotReservationStore` port.

Persists dark-kitchen delivery-window bookings (COM-304): the capacity write path that backs
availability (COM-302). Shares the request-scoped :class:`Session` with the order repository, so a
reservation added here is committed atomically by the same unit of work that persists the order
(``SqlOrderRepository.add`` calls ``commit``); ``reserve`` and ``release`` therefore ``flush`` but
never ``commit``. Capacity is enforced per exact ``(service_zone, delivery_date,
delivery_time_slot)``, where the service zone is the delivery postcode.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import SlotReservationModel
from app.domain.errors import SlotUnavailableError


class SqlSlotReservationStore:
    """Persistence adapter for dark-kitchen slot reservations backed by a SQLAlchemy Session."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def booked_counts(self, zip_code: str, delivery_date: date) -> Mapping[str, int]:
        stmt = (
            select(SlotReservationModel.delivery_time_slot, func.count())
            .where(
                SlotReservationModel.service_zone == zip_code,
                SlotReservationModel.delivery_date == delivery_date,
            )
            .group_by(SlotReservationModel.delivery_time_slot)
        )
        return {slot: count for slot, count in self._db.execute(stmt).all()}

    def reserve(
        self,
        *,
        zip_code: str,
        delivery_date: date,
        slot: str,
        order_id: uuid.UUID,
        capacity: int,
    ) -> None:
        # Count the window's current bookings, then book one more if there is headroom. Flushing
        # each insert into the transaction makes it visible to the next count, so several reserves
        # in one unit of work accumulate correctly (a concurrent transaction is a separate concern;
        # the unique ``order_id`` constraint still prevents double-booking the same order).
        if self._count(zip_code=zip_code, delivery_date=delivery_date, slot=slot) >= capacity:
            raise SlotUnavailableError(zip_code=zip_code, delivery_date=delivery_date, slot=slot)
        self._db.add(
            SlotReservationModel(
                order_id=order_id,
                service_zone=zip_code,
                delivery_date=delivery_date,
                delivery_time_slot=slot,
            )
        )
        # Flush, not commit: the reservation is made durable by the order it is created alongside,
        # so a later failure in the same request (e.g. a declined payment) rolls it back too.
        self._db.flush()

    def release(self, *, order_id: uuid.UUID) -> None:
        # Idempotent: releasing a non-existent reservation affects zero rows. No commit -- the
        # delete is committed by the cancel unit of work that persists the order's new status.
        self._db.execute(
            delete(SlotReservationModel).where(SlotReservationModel.order_id == order_id)
        )

    def _count(self, *, zip_code: str, delivery_date: date, slot: str) -> int:
        stmt = select(func.count()).where(
            SlotReservationModel.service_zone == zip_code,
            SlotReservationModel.delivery_date == delivery_date,
            SlotReservationModel.delivery_time_slot == slot,
        )
        return self._db.execute(stmt).scalar_one()
