"""Domain-level failures, raised before anything reaches a store."""

from __future__ import annotations


class NotificationError(Exception):
    """Base class for every notification domain error."""


class InvalidNotification(NotificationError, ValueError):
    """A notification was constructed in a state the domain does not allow.

    It subclasses :class:`ValueError` too, so callers that already treat bad input
    generically keep working while the API layer can still catch the domain base class.
    """
