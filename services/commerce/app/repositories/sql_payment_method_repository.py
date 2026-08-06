"""SQLAlchemy adapter implementing the :class:`~app.domain.repositories.PaymentMethodRepository`.

Maps the :class:`~app.domain.payment_method.SavedPaymentMethod` entity onto the ``payment_methods``
table and back (COM-207). Every query is owner-scoped by ``user_id`` so one user can never list,
read or delete another's stored instrument — also re-checked at the HTTP edge.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import PaymentMethodModel
from app.domain.enums import PaymentMethodType
from app.domain.payment_method import SavedPaymentMethod


class SqlPaymentMethodRepository:
    """Persistence adapter for saved payment methods backed by a SQLAlchemy :class:`Session`."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, method: SavedPaymentMethod) -> SavedPaymentMethod:
        model = self._to_model(method)
        self._db.add(model)
        self._db.commit()
        self._db.refresh(model)
        return self._to_domain(model)

    def list_for_user(self, user_id: uuid.UUID) -> list[SavedPaymentMethod]:
        stmt = (
            select(PaymentMethodModel)
            .where(PaymentMethodModel.user_id == user_id)
            .order_by(PaymentMethodModel.created_at.desc(), PaymentMethodModel.id)
        )
        models = self._db.execute(stmt).scalars().all()
        return [self._to_domain(model) for model in models]

    def get(self, method_id: uuid.UUID, *, user_id: uuid.UUID) -> SavedPaymentMethod | None:
        stmt = select(PaymentMethodModel).where(
            PaymentMethodModel.id == method_id, PaymentMethodModel.user_id == user_id
        )
        model = self._db.execute(stmt).scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    def delete(self, method_id: uuid.UUID, *, user_id: uuid.UUID) -> bool:
        stmt = delete(PaymentMethodModel).where(
            PaymentMethodModel.id == method_id, PaymentMethodModel.user_id == user_id
        )
        result = self._db.execute(stmt)
        self._db.commit()
        return result.rowcount > 0

    def _to_model(self, method: SavedPaymentMethod) -> PaymentMethodModel:
        return PaymentMethodModel(
            id=method.id,
            user_id=method.user_id,
            type=method.type.value,
            token=method.token,
            brand=method.brand,
            last4=method.last4,
            exp_month=method.exp_month,
            exp_year=method.exp_year,
            created_at=method.created_at,
        )

    def _to_domain(self, model: PaymentMethodModel) -> SavedPaymentMethod:
        return SavedPaymentMethod(
            id=model.id,
            user_id=model.user_id,
            type=PaymentMethodType(model.type),
            token=model.token,
            brand=model.brand,
            last4=model.last4,
            exp_month=model.exp_month,
            exp_year=model.exp_year,
            created_at=model.created_at,
        )
