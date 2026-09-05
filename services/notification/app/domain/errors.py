"""Domain-level failures, raised before anything reaches a store."""

from __future__ import annotations


class NotificationError(Exception):
    """Base class for every notification domain error."""


class InvalidNotification(NotificationError, ValueError):
    """A notification was constructed in a state the domain does not allow.

    It subclasses :class:`ValueError` too, so callers that already treat bad input
    generically keep working while the API layer can still catch the domain base class.
    """


class InvalidDedupeKey(NotificationError, ValueError):
    """A dedupe key could not be derived from the given (event, user, type) triple.

    Raised rather than defaulted, because every fallback is worse: a blank event id would
    silently merge unrelated events onto one key and suppress notifications for good.
    """
