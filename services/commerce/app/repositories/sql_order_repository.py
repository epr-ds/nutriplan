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

from app.db.models import AddressModel, OrderItemModel, OrderModel
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus
from app.domain.money import Money
from app.domain.order import Order, OrderItem


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

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        status: OrderStatus | None = None,
        from_date: date | None = None,
    ) -> list[Order]:
        stmt = select(OrderModel).where(OrderModel.user_id == user_id)
        if status is not None:
            stmt = stmt.where(OrderModel.status == status.value)
        if from_date is not None:
            start = datetime.combine(from_date, time.min, tzinfo=UTC)
            stmt = stmt.where(OrderModel.created_at >= start)
        stmt = stmt.order_by(OrderModel.created_at.desc(), OrderModel.id)
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
            items=items,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
