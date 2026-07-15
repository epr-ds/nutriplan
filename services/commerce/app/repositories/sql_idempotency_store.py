"""SQLAlchemy adapter implementing the :class:`~app.application.idempotency.IdempotencyStore` port.

Backs the ``Idempotency-Key`` de-duplication for create-order (COM-209). Shares the request-scoped
:class:`Session` with the order repository so a lookup sees anything committed earlier in the same
request. ``save`` relies on the ``(user_id, idempotency_key)`` unique constraint as the concurrency
backstop: if a simultaneous request recorded the same key first, the insert raises
:class:`IntegrityError`, which we swallow — the winner's order is exactly the result a retry
replays.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.idempotency import IdempotencyRecord
from app.db.models import IdempotencyKeyModel


class SqlIdempotencyStore:
    """Persistence adapter for idempotency keys backed by a SQLAlchemy :class:`Session`."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def find(self, key: str, *, user_id: uuid.UUID) -> IdempotencyRecord | None:
        stmt = select(IdempotencyKeyModel).where(
            IdempotencyKeyModel.user_id == user_id,
            IdempotencyKeyModel.idempotency_key == key,
        )
        model = self._db.execute(stmt).scalar_one_or_none()
        if model is None:
            return None
        return IdempotencyRecord(
            key=model.idempotency_key,
            user_id=model.user_id,
            order_id=model.order_id,
            request_fingerprint=model.request_fingerprint,
        )

    def save(
        self, key: str, *, user_id: uuid.UUID, order_id: uuid.UUID, request_fingerprint: str
    ) -> None:
        self._db.add(
            IdempotencyKeyModel(
                user_id=user_id,
                idempotency_key=key,
                order_id=order_id,
                request_fingerprint=request_fingerprint,
            )
        )
        try:
            self._db.commit()
        except IntegrityError:
            # A concurrent request recorded this key first; its order is the canonical result a
            # retry will replay, so the collision is benign — discard our duplicate and move on.
            self._db.rollback()
