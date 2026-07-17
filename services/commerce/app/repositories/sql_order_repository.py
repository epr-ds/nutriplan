"""SQLAlchemy adapter implementing the :class:`~app.domain.repositories.OrderRepository` port.

Maps the ``Order`` aggregate onto the ``orders``/``order_items``/``addresses``
tables and back. Reads are always owner-scoped by ``user_id`` so one user can never load another's
order (the ownership guarantee COM-108 later enforces at the HTTP edge).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AddressModel, OrderItemModel, OrderModel, OrderStatusHistoryModel
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.money import Money
from app.domain.order import Order, OrderItem, OrderStatusChange
from app.domain.payment import PaymentStatus


class SqlOrderRepository:
    """Persistence adapter for orders backed by a SQLAlchemy :class:`Session`."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, order: Order) -> Order:
        address_model = self._address_to_model(order.delivery_address, order.user_id)
        order_model = self._order_to_model(order)
        order_model.delivery_address = address_model
        self._db.add(order_model)
        self._db.commit()
        self._db.refresh(order_model)
        return self._to_domain(order_model)

    def get(self, order_id: uuid.UUID, *, user_id: uuid.UUID) -> Order | None:
        stmt = select(OrderModel).where(OrderModel.id == order_id, OrderModel.user_id == user_id)
        model = self._db.execute(stmt).scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    def update(self, order: Order) -> Order:
        """Persist mutations to an existing order: its status/timestamp and any new history rows.

        History is append-only, so we compare the aggregate's ``status_history`` length against the
        rows already stored and insert only the new tail (keyed by ``position``). Owner-scoping is
        the loader's job — callers reach this only after an owner-scoped :meth:`get`.
        """
        stmt = select(OrderModel).where(OrderModel.id == order.id)
        model = self._db.execute(stmt).scalar_one()
        model.status = order.status.value
        model.updated_at = order.updated_at
        stored = len(model.status_history)
        for position in range(stored, len(order.status_history)):
            change = order.status_history[position]
            model.status_history.append(
                OrderStatusHistoryModel(
                    position=position,
                    from_status=change.from_status.value,
                    to_status=change.to_status.value,
                    occurred_at=change.occurred_at,
                )
            )
        self._db.commit()
        self._db.refresh(model)
        return self._to_domain(model)

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        status: OrderStatus | None = None,
        from_date: date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Order]:
        stmt = select(OrderModel).where(OrderModel.user_id == user_id)
        if status is not None:
            stmt = stmt.where(OrderModel.status == status.value)
        if from_date is not None:
            start = datetime.combine(from_date, time.min, tzinfo=UTC)
            stmt = stmt.where(OrderModel.created_at >= start)
        stmt = stmt.order_by(OrderModel.created_at.desc(), OrderModel.id)
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        models = self._db.execute(stmt).scalars().all()
        return [self._to_domain(model) for model in models]

    def _address_to_model(self, address: Address, user_id: uuid.UUID) -> AddressModel:
        return AddressModel(
            id=address.id,
            user_id=address.user_id or user_id,
            street=address.street,
            apartment=address.apartment,
            city=address.city,
            state=address.state,
            zip_code=address.zip_code,
            country=address.country,
            instructions=address.instructions,
        )

    def _order_to_model(self, order: Order) -> OrderModel:
        return OrderModel(
            id=order.id,
            user_id=order.user_id,
            status=order.status.value,
            fulfillment_type=order.fulfillment_type.value,
            provider_id=order.provider_id,
            delivery_date=order.delivery_date,
            delivery_time_slot=order.delivery_time_slot,
            notes=order.notes,
            subtotal_amount=order.subtotal.amount,
            delivery_fee_amount=order.delivery_fee.amount,
            total_amount=order.total.amount,
            currency=order.total.currency,
            estimated_delivery=order.estimated_delivery,
            tracking_url=order.tracking_url,
            payment_status=order.payment_status.value if order.payment_status else None,
            payment_provider=order.payment_provider,
            payment_charge_id=order.payment_charge_id,
            payment_voucher_reference=order.payment_voucher_reference,
            payment_voucher_expires_at=order.payment_voucher_expires_at,
            payment_voucher_barcode_url=order.payment_voucher_barcode_url,
            items=[
                OrderItemModel(
                    id=item.id,
                    position=index,
                    name=item.name,
                    quantity=item.quantity,
                    unit=item.unit,
                    unit_price_amount=item.unit_price.amount,
                    line_total_amount=item.line_total.amount,
                )
                for index, item in enumerate(order.items)
            ],
            status_history=[
                OrderStatusHistoryModel(
                    position=index,
                    from_status=change.from_status.value,
                    to_status=change.to_status.value,
                    occurred_at=change.occurred_at,
                )
                for index, change in enumerate(order.status_history)
            ],
        )

    def _to_domain(self, model: OrderModel) -> Order:
        currency = model.currency
        address = Address(
            id=model.delivery_address.id,
            user_id=model.delivery_address.user_id,
            street=model.delivery_address.street,
            apartment=model.delivery_address.apartment,
            city=model.delivery_address.city,
            state=model.delivery_address.state,
            zip_code=model.delivery_address.zip_code,
            country=model.delivery_address.country,
            instructions=model.delivery_address.instructions,
        )
        items = [
            OrderItem(
                id=item.id,
                name=item.name,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=Money(item.unit_price_amount, currency),
                line_total=Money(item.line_total_amount, currency),
            )
            for item in model.items
        ]
        status_history = [
            OrderStatusChange(
                from_status=OrderStatus(entry.from_status),
                to_status=OrderStatus(entry.to_status),
                occurred_at=entry.occurred_at,
            )
            for entry in model.status_history
        ]
        return Order(
            id=model.id,
            user_id=model.user_id,
            status=OrderStatus(model.status),
            fulfillment_type=FulfillmentType(model.fulfillment_type),
            provider_id=model.provider_id,
            delivery_address=address,
            delivery_date=model.delivery_date,
            delivery_time_slot=model.delivery_time_slot,
            notes=model.notes,
            subtotal=Money(model.subtotal_amount, currency),
            delivery_fee=Money(model.delivery_fee_amount, currency),
            total=Money(model.total_amount, currency),
            estimated_delivery=model.estimated_delivery,
            tracking_url=model.tracking_url,
            payment_status=PaymentStatus(model.payment_status) if model.payment_status else None,
            payment_provider=model.payment_provider,
            payment_charge_id=model.payment_charge_id,
            payment_voucher_reference=model.payment_voucher_reference,
            payment_voucher_expires_at=model.payment_voucher_expires_at,
            payment_voucher_barcode_url=model.payment_voucher_barcode_url,
            items=items,
            status_history=status_history,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
