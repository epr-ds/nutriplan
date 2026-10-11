"""Event → notification mapping / routing rules (NTF-205).

This module provides the router that maps event types to the handlers that should process
them. The router itself is simple -- it is just a lookup function -- but it is the critical
link between the event bus and the notification logic.

The routing table is a simple mapping from event type string to a sequence of handler import
paths. The dispatcher looks up handlers by import in :mod:`app.events.factory`, not through
this class, so this router is only concerned with *which* handlers, not *how* they are found.

Routing rules:

1. A mapper is a function of event type alone -- same type → same handlers every time.
2. Multiple handlers per type are supported, and ordering matters:
   - if handler A fails (raises ``EventError``), B and C are never called
   - if handler A raises a transient exception, B and C are never called
     (retry happens for the whole event, not per-handler)
3. A type with zero handlers is treated the same as unknown type (acked, not dead-lettered)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


class EventRouter:
    """Route event types to their handler import paths.

    The lookup table is passed in at construction and never modified -- routing rules are
    static configuration, not runtime decisions. This is by design: changing which events
    trigger which notifications is a deployment-time decision, not an in-flight one.
    """

    def __init__(self, handlers_by_type: Mapping[str, Sequence[str]]) -> None:
        """Build a router with the given mapping.

        :param handlers_by_type: A mapping from event type to a sequence of handler import paths.
        :raises TypeError: If any handler list contains ``None`` as a value.
        """
        # Validate that no handler list contains None values.
        for event_type, handlers in handlers_by_type.items():
            if any(h is None for h in handlers):
                raise TypeError("handler list for event type cannot contain None")
        self._handlers_by_type = dict(handlers_by_type)

    def get_handlers(self, event_type: str) -> Sequence[str]:
        """Return a **copy** of the handler import paths for ``event_type``.

        Returning a copy prevents callers from mutating the internal routing table.
        :param event_type: The event type to look up.
        :return: An ordered list of handler import paths, or an empty list if the
                 type is unknown or has no handlers.
        """
        # Return a new list to ensure callers cannot modify the internal mapping.
        handlers = self._handlers_by_type.get(event_type, [])
        return list(handlers)

    def handled_types(self) -> tuple[str, ...]:
        """Return all event types that have handlers, sorted."""
        return tuple(sorted(self._handlers_by_type.keys()))
