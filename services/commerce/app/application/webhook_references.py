"""Shared helper: map a webhook's echoed reference back to an order id (COM-206 / COM-303).

Both the payment webhook (COM-206) and the kitchen status webhook (COM-303) authenticate by
signature and carry the order id as a string ``reference`` -- the create-order flow hands the
provider/kitchen ``str(order.id)``. Turning that reference back into a ``uuid.UUID`` (and treating a
non-UUID as a not-found order rather than leaking that it was merely un-parseable) is identical for
both, so it lives here once.
"""

from __future__ import annotations

import uuid

from app.domain.errors import OrderNotFoundError


def reference_to_order_id(reference: str) -> uuid.UUID:
    """Map a webhook's echoed reference back to an order id.

    A well-formed webhook carries ``str(order.id)`` as its reference. A reference that is not a
    UUID cannot name any order of ours, so it is reported as a not-found order (a 404) rather than
    leaking that it was merely un-parseable.
    """
    try:
        return uuid.UUID(reference)
    except ValueError as exc:
        raise OrderNotFoundError(reference) from exc
