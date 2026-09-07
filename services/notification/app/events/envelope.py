"""The inbound wire envelope, and how a raw stream payload becomes one (NTF-201).

Commerce wraps every order event in a small, self-describing envelope (COM-109) and appends
it to a Redis stream as a single JSON ``payload`` field::

    {
      "schemaVersion": 1,
      "id": "<uuid4>",                 # unique per publish
      "type": "order.created",
      "occurredAt": "2026-07-12T21:00:00+00:00",
      "data": { "orderId": "...", "userId": "..." }
    }

:func:`parse_envelope` is the inverse of that publisher, and the only place in this service
that trusts bytes off the bus. Everything past this function works with a typed
:class:`EventEnvelope` and can assume the shape is sound.

**Strict on structure, tolerant of additions.** An unrecognised *top-level* key is ignored
rather than rejected, and so is an unrecognised key inside ``data``. That tolerance is what
lets commerce add a field without a synchronised deploy: additive change is the common case,
and a consumer that rejected it would turn every ordinary producer release into an outage on
this side of the bus. What is *not* tolerated is a missing or unreadable required field --
that is a defect, and guessing a value for it would put a wrong notification in front of a
user.

**Two identifiers, and NTF-202 must not confuse them.** :attr:`EventEnvelope.event_id` is
assigned by the producer and travels *inside* the payload; the Redis stream entry id is
assigned by the broker and lives outside it (see
:attr:`~app.events.consumer.DeliveredEvent.delivery_id`). They behave differently under
replay: a redelivery of the same entry keeps both, but NTF-204 re-publishing a parked event
mints a **new entry id** while the envelope id stays put. So NTF-103's dedupe key must be
derived from ``event_id`` -- keying it on the delivery id would let a dead-letter replay
sail past deduplication and hand the user a second copy of a notification they already have.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.events.errors import MalformedEvent

REQUIRED_FIELDS = ("schemaVersion", "id", "type", "occurredAt")
"""Envelope keys with no sensible default. ``data`` is deliberately absent -- see below."""


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """One validated domain event, ready to route on.

    Immutable because a handler must not be able to edit an event on its way to the next
    one, and because the dispatcher may hand the same envelope to several handlers.
    """

    schema_version: int
    event_id: str
    type: str
    occurred_at: datetime
    data: Mapping[str, Any] = field(default_factory=dict)

    def require(self, key: str) -> Any:
        """Return ``data[key]``, or raise :class:`MalformedEvent` naming what was missing.

        Handlers use this rather than indexing so a producer defect surfaces as a permanent,
        parkable failure with a legible message instead of a ``KeyError`` from somewhere
        deep in a handler, which the dispatcher would have to treat as retryable.
        """
        try:
            return self.data[key]
        except KeyError:
            raise MalformedEvent(
                f"event {self.event_id} ({self.type}) has no data field {key!r}"
            ) from None


def parse_envelope(payload: str | bytes | Mapping[str, Any]) -> EventEnvelope:
    """Parse a raw stream payload into a validated :class:`EventEnvelope`.

    Accepts the JSON text as published, or an already-decoded mapping (which is what the
    in-process adapter and most tests hand over). Raises :class:`MalformedEvent` -- a
    permanent failure -- for anything it cannot read.
    """
    raw = _decode(payload)

    missing = [name for name in REQUIRED_FIELDS if name not in raw]
    if missing:
        raise MalformedEvent(f"envelope is missing required field(s): {', '.join(missing)}")

    return EventEnvelope(
        schema_version=_schema_version(raw["schemaVersion"]),
        event_id=_identifier(raw["id"], "id"),
        type=_identifier(raw["type"], "type"),
        occurred_at=_occurred_at(raw["occurredAt"]),
        # Absent ``data`` becomes an empty mapping rather than an error: the registry's
        # required-field check runs next and reports "missing orderId, userId", which tells
        # an operator far more than "missing data" would.
        data=_data(raw.get("data", {})),
    )


def _decode(payload: str | bytes | Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the payload as a mapping, whether it arrived as JSON text or already parsed."""
    if isinstance(payload, Mapping):
        return payload
    try:
        parsed = json.loads(payload)
    except (TypeError, ValueError) as exc:
        raise MalformedEvent(f"payload is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise MalformedEvent(f"payload is a JSON {type(parsed).__name__}, expected an object")
    return parsed


def _schema_version(value: Any) -> int:
    """Validate the schema version: a positive integer, and never a bool.

    ``isinstance(True, int)`` is true in Python, so a ``true`` on the wire would otherwise
    be read as version 1 -- a nonsense envelope quietly accepted as the current one.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise MalformedEvent(f"schemaVersion must be an integer, got {type(value).__name__}")
    if value < 1:
        raise MalformedEvent(f"schemaVersion must be positive, got {value}")
    return value


def _identifier(value: Any, name: str) -> str:
    """Validate a required, non-blank string field."""
    if not isinstance(value, str):
        raise MalformedEvent(f"{name} must be a string, got {type(value).__name__}")
    text = value.strip()
    if not text:
        raise MalformedEvent(f"{name} must not be blank")
    return text


def _occurred_at(value: Any) -> datetime:
    """Parse the ISO-8601 timestamp, insisting it carries an offset.

    A naive timestamp is rejected rather than assumed to be UTC. This service decides when
    to stay quiet using the user's own time zone (NTF-104), so an hour of drift is not a
    rounding error -- it is a push notification at three in the morning. And because the
    consumer, the producer and the user can each be in different zones, there is no default
    here that is right more often than it is wrong.
    """
    if not isinstance(value, str):
        raise MalformedEvent(f"occurredAt must be a string, got {type(value).__name__}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise MalformedEvent(f"occurredAt is not an ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise MalformedEvent(f"occurredAt must carry a UTC offset, got {value!r}")
    return parsed


def _data(value: Any) -> Mapping[str, Any]:
    """Validate the type-specific payload is an object, and copy it so it cannot be edited."""
    if not isinstance(value, Mapping):
        raise MalformedEvent(f"data must be an object, got {type(value).__name__}")
    return dict(value)
