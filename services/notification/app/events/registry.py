"""The versioned event-schema registry and its compatibility rules (NTF-201, AC2).

The registry is this build's answer to "which events do I actually know how to read?". It
holds one :class:`EventSchema` per ``(type, version)`` pair and, given a parsed envelope,
returns a :class:`Compatibility` verdict that the dispatcher turns into an ack, a park, or a
retry.

Four verdicts, and the reasoning behind each is the substance of this module:

``SUPPORTED``
    The type is registered at this exact version and every field the schema requires is
    present. The only verdict that reaches a handler.

``UNKNOWN_TYPE``
    A type this build has never heard of. **Not an error.** A producer adding an event type
    is routine, and a stream is a broadcast medium -- being sent something you do not care
    about is the normal condition, not a fault. These are acknowledged and dropped. Parking
    them instead would fill the dead-letter queue with ordinary traffic, and a queue that
    alarms constantly is a queue nobody reads, which is how the one genuine failure in it
    gets missed.

``UNSUPPORTED_VERSION``
    A type we know, at a version we do not. This is the interesting one, and it is
    deliberately **not** treated as "close enough". It is tempting to accept a higher version
    when the fields we need happen to still be there -- but a version bump is precisely the
    producer's signal that the meaning changed, and the fields most likely to be re-specified
    are the ones we read. ``toStatus: "cancelled"`` meaning "the user cancelled" in v1 and
    "the kitchen rejected it" in v2 is the same string, the same schema shape, and a
    completely different notification to send. Guessing sends the wrong one to a real person.
    So the event is parked, where NTF-204 can replay it to a build that understands it. This
    is the one permanent failure a deploy actually fixes.

``MISSING_FIELDS``
    Registered type, registered version, but the payload does not carry what that version
    promised. The producer is broken; parked for a human.

The schemas seeded below mirror ``services/commerce/app/events/envelope.py`` exactly, and
:mod:`tests.test_event_registry` pins them against that file's real output. A registry that
drifts from the publisher is worse than no registry: it would reject valid traffic while
reporting, in its own terms, that everything is fine.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum

from app.events.envelope import EventEnvelope

ORDER_CREATED = "order.created"
ORDER_CONFIRMED = "order.confirmed"
ORDER_STATUS_CHANGED = "order.status_changed"

ORDER_EVENT_VERSION = 1
"""The commerce envelope's ``SCHEMA_VERSION``. Bumping it there requires a schema here."""


class Compatibility(Enum):
    """What the registry makes of one envelope."""

    SUPPORTED = "supported"
    UNKNOWN_TYPE = "unknown_type"
    UNSUPPORTED_VERSION = "unsupported_version"
    MISSING_FIELDS = "missing_fields"

    @property
    def is_supported(self) -> bool:
        """True only for the verdict that may reach a handler."""
        return self is Compatibility.SUPPORTED

    @property
    def should_dead_letter(self) -> bool:
        """True for verdicts worth keeping; an unknown type is dropped, not parked."""
        return self in {Compatibility.UNSUPPORTED_VERSION, Compatibility.MISSING_FIELDS}


@dataclass(frozen=True, slots=True)
class Verdict:
    """A compatibility outcome plus the detail needed to explain it in a log or a park."""

    compatibility: Compatibility
    reason: str
    missing: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        """Truthy when the envelope may be handled."""
        return self.compatibility.is_supported


@dataclass(frozen=True, slots=True)
class EventSchema:
    """One version of one event type, described by what a consumer may rely on.

    ``required`` lists the ``data`` keys this build reads. It is intentionally a *consumer's*
    view rather than a transcription of the producer's full payload: recording fields we
    never look at would make an unrelated producer change fail validation here for no reason.
    """

    type: str
    version: int
    required: frozenset[str] = field(default_factory=frozenset)

    @property
    def key(self) -> tuple[str, int]:
        """The ``(type, version)`` pair this schema is registered under."""
        return (self.type, self.version)

    def missing_from(self, data: Mapping[str, object]) -> tuple[str, ...]:
        """Return the required keys absent from ``data``, sorted for a stable message."""
        return tuple(sorted(name for name in self.required if name not in data))


ORDER_EVENT_SCHEMAS: tuple[EventSchema, ...] = (
    # ``order.created`` carries only the identifiers -- see commerce's ``_data``.
    EventSchema(ORDER_CREATED, ORDER_EVENT_VERSION, frozenset({"orderId", "userId"})),
    EventSchema(
        ORDER_CONFIRMED,
        ORDER_EVENT_VERSION,
        frozenset({"orderId", "userId", "fromStatus", "toStatus"}),
    ),
    EventSchema(
        ORDER_STATUS_CHANGED,
        ORDER_EVENT_VERSION,
        frozenset({"orderId", "userId", "fromStatus", "toStatus"}),
    ),
)
"""The commerce order lifecycle, as this service is prepared to read it (COM-109)."""


class EventSchemaRegistry:
    """Every ``(type, version)`` this build can interpret, and the verdict for one envelope."""

    def __init__(self, schemas: Iterable[EventSchema] = ()) -> None:
        self._schemas: dict[tuple[str, int], EventSchema] = {}
        self._versions: dict[str, set[int]] = {}
        for schema in schemas:
            self.register(schema)

    def register(self, schema: EventSchema) -> None:
        """Add a schema, refusing to replace one already registered.

        Silent replacement would let an import-order accident decide which definition of an
        event type wins, and the losing one would simply never be consulted again. Two
        schemas for one ``(type, version)`` is a programming error, so it is raised here
        where a test or an import will find it, not at three in the morning.
        """
        if schema.key in self._schemas:
            raise ValueError(f"schema already registered for {schema.type} v{schema.version}")
        self._schemas[schema.key] = schema
        self._versions.setdefault(schema.type, set()).add(schema.version)

    def get(self, event_type: str, version: int) -> EventSchema | None:
        """Return the registered schema for a ``(type, version)``, or ``None``."""
        return self._schemas.get((event_type, version))

    def knows_type(self, event_type: str) -> bool:
        """True when *some* version of this type is registered."""
        return event_type in self._versions

    def versions_for(self, event_type: str) -> tuple[int, ...]:
        """Every registered version of a type, ascending; empty when the type is unknown."""
        return tuple(sorted(self._versions.get(event_type, ())))

    @property
    def schemas(self) -> tuple[EventSchema, ...]:
        """Every registered schema, ordered by type then version."""
        return tuple(self._schemas[key] for key in sorted(self._schemas))

    def check(self, envelope: EventEnvelope) -> Verdict:
        """Decide whether ``envelope`` may be handled, and say why when it may not."""
        if not self.knows_type(envelope.type):
            return Verdict(
                Compatibility.UNKNOWN_TYPE,
                f"no schema registered for event type {envelope.type!r}",
            )

        schema = self.get(envelope.type, envelope.schema_version)
        if schema is None:
            known = ", ".join(f"v{version}" for version in self.versions_for(envelope.type))
            return Verdict(
                Compatibility.UNSUPPORTED_VERSION,
                f"{envelope.type} v{envelope.schema_version} is not understood "
                f"by this build (knows {known})",
            )

        missing = schema.missing_from(envelope.data)
        if missing:
            return Verdict(
                Compatibility.MISSING_FIELDS,
                f"{envelope.type} v{envelope.schema_version} is missing "
                f"required data field(s): {', '.join(missing)}",
                missing=missing,
            )

        return Verdict(Compatibility.SUPPORTED, "ok")


def default_registry() -> EventSchemaRegistry:
    """The registry the service runs with: the commerce order lifecycle at v1.

    Built fresh on each call rather than shared as a module-level singleton, so a test that
    registers an extra schema cannot leak it into the next test.
    """
    return EventSchemaRegistry(ORDER_EVENT_SCHEMAS)
