"""The versioned wire envelope for commerce order events (COM-109).

A published event is wrapped in a small, self-describing envelope so a downstream consumer (the P5
notification service) can route and evolve safely::

    {
      "schemaVersion": 1,
      "id": "<uuid4>",                 # unique per publish, for idempotent consumers
      "type": "order.created",         # order.created | order.confirmed | order.status_changed
      "occurredAt": "2026-07-12T21:00:00+00:00",
      "data": { ... }                  # camelCase, type-specific
    }

The ``type`` distinguishes the three lifecycle events the story calls out: a placement
(``order.created``), the specific ``pending -> confirmed`` move (``order.confirmed``), and any other
transition (``order.status_changed``). Bumping :data:`SCHEMA_VERSION` is how the payload evolves
without breaking existing consumers.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.domain.enums import OrderStatus
from app.domain.events import DomainEvent, OrderCreated

SCHEMA_VERSION = 1

EVENT_TYPE_CREATED = "order.created"
EVENT_TYPE_CONFIRMED = "order.confirmed"
EVENT_TYPE_STATUS_CHANGED = "order.status_changed"


def event_type(event: DomainEvent) -> str:
    """Map a domain event to its bus event ``type``."""
    if isinstance(event, OrderCreated):
        return EVENT_TYPE_CREATED
    if event.to_status is OrderStatus.CONFIRMED:
        return EVENT_TYPE_CONFIRMED
    return EVENT_TYPE_STATUS_CHANGED


def _data(event: DomainEvent) -> dict[str, Any]:
    if isinstance(event, OrderCreated):
        return {"orderId": str(event.order_id), "userId": str(event.user_id)}
    return {
        "orderId": str(event.order_id),
        "userId": str(event.user_id),
        "fromStatus": event.from_status.value,
        "toStatus": event.to_status.value,
    }


def to_envelope(event: DomainEvent, *, event_id: uuid.UUID | None = None) -> dict[str, Any]:
    """Serialize a domain event to its versioned, JSON-native envelope.

    ``event_id`` is generated per publish unless supplied (injected in tests for determinism). The
    returned dict contains only JSON-native types, so an adapter can ``json.dumps`` it directly.
    """
    return {
        "schemaVersion": SCHEMA_VERSION,
        "id": str(event_id or uuid.uuid4()),
        "type": event_type(event),
        "occurredAt": event.occurred_at.isoformat(),
        "data": _data(event),
    }
