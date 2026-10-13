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


class NotificationNotFound(NotificationError):
    """The requested notification is not visible to the caller (NTF-105).

    Deliberately raised for three different situations -- the id never existed, it aged out
    of the rolling window, or it belongs to somebody else -- because the API renders all of
    them as the same ``404``. Distinguishing them on the wire would turn the endpoint into an
    oracle: a caller could enumerate UUIDs and learn which ones are real notifications
    belonging to other users. The store enforces the same rule by returning ``None`` for all
    three, so this error carries no more information than the store was willing to give.
    """


class InvalidFeedQuery(NotificationError, ValueError):
    """A feed page was requested with bounds the service will not serve (NTF-105).

    Page size is capped rather than honoured: an unbounded ``limit`` would let one request
    materialize a user's entire retained feed, and the cost of that lands on the shared Redis
    every other request depends on.
    """


class InvalidPreferences(NotificationError, ValueError):
    """Notification preferences were given in a state the domain will not store (NTF-104).

    Preferences are the one part of this service a *user* writes directly, so the invariants
    are enforced here rather than trusted from the edge: an unknown IANA zone, a quiet-hours
    window whose ends coincide, or a duplicated per-type row would each otherwise be stored
    and then silently mis-evaluated on every notification for as long as the user kept them.
    """
