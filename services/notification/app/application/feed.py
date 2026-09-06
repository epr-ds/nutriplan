"""The in-app feed use cases (NTF-105): read the feed, count what's unread, mark one read.

These three operations are one cohesive concern -- everything a signed-in user does *to their
own feed* -- so they share a service rather than being split one-per-module. What they really
share is the rule that makes the feed safe: **the owner comes from the verified token and is
passed to every store call**. There is no code path here that takes a user id from the caller.

Two decisions in this module are worth reading before changing anything.

**Why ``has_more`` can be trusted.** The store's ``list_for_user`` is documented to return a
*short* page when entries in the requested slice have expired since they were indexed, and to
warn callers not to infer "there are more" from a full page. That would normally make an
honest ``hasMore`` impossible without a second count. It is possible here because expiry is
**monotonic in feed order**: every record's lease runs from its own ``created_at`` with one
uniform TTL (NTF-102 sets ``ex`` to the *remaining* window precisely so a replayed old event
cannot buy itself a fresh one), and the feed is ordered newest-first. So the live records are
always a prefix of the index and a hole implies the tail. Asking for one row beyond the page
therefore answers "is there another one?" truthfully, and costs one index slot rather than a
second round trip. If a future story gives records individual lifetimes, that argument
collapses and this must become a real count.

**Why the unread count is a separate read.** The page and the count are two store reads with
no transaction between them, so a mark-read landing in the gap can produce a page whose items
disagree with the badge by one. Making them atomic would mean holding a lock across a user's
feed read -- a real cost on the shared Redis -- to fix a discrepancy that the next poll
corrects on its own. The count is documented as a snapshot, not an invariant of the page.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.domain.errors import InvalidFeedQuery, NotificationNotFound
from app.domain.notification import Notification
from app.domain.repositories import NotificationRepository

DEFAULT_PAGE_SIZE = 20
"""Enough to fill a phone screen and a scroll beyond it, without over-fetching on open."""

MAX_PAGE_SIZE = 100
"""The largest page served. See :class:`~app.domain.errors.InvalidFeedQuery` for why."""


@dataclass(frozen=True, slots=True)
class FeedQuery:
    """A request for one page of a user's feed.

    Pagination is 1-based ``page``/``limit`` on the wire (matching Commerce's list endpoints,
    so the mobile client uses one idiom everywhere) and converted to the store's
    ``limit``/``offset`` here -- the one place the two conventions meet.
    """

    user_id: uuid.UUID
    unread_only: bool = False
    page: int = 1
    limit: int = DEFAULT_PAGE_SIZE

    def __post_init__(self) -> None:
        if self.page < 1:
            raise InvalidFeedQuery(f"page must be at least 1, got {self.page}")
        if self.limit < 1:
            raise InvalidFeedQuery(f"limit must be at least 1, got {self.limit}")
        if self.limit > MAX_PAGE_SIZE:
            raise InvalidFeedQuery(f"limit must be at most {MAX_PAGE_SIZE}, got {self.limit}")

    @property
    def offset(self) -> int:
        """How many entries the store should skip to reach this page."""
        return (self.page - 1) * self.limit


@dataclass(frozen=True, slots=True)
class FeedPage:
    """One page of the feed plus the badge count, as the API returns it."""

    items: tuple[Notification, ...]
    unread_count: int
    page: int
    limit: int
    has_more: bool

    def __len__(self) -> int:
        return len(self.items)


class NotificationFeed:
    """The user-facing read/mark-read side of the notification store."""

    def __init__(self, repository: NotificationRepository) -> None:
        self._repository = repository

    @property
    def repository(self) -> NotificationRepository:
        """The store this feed reads, exposed so callers can assert on what was persisted."""
        return self._repository

    def page(self, query: FeedQuery) -> FeedPage:
        """Return one page of ``query.user_id``'s notifications, newest first.

        One extra row is requested and then dropped; see the module docstring for why that is
        a truthful ``has_more`` rather than a guess.
        """
        window = self._repository.list_for_user(
            query.user_id,
            unread_only=query.unread_only,
            limit=query.limit + 1,
            offset=query.offset,
        )
        return FeedPage(
            items=tuple(window[: query.limit]),
            unread_count=self._repository.count_unread(query.user_id),
            page=query.page,
            limit=query.limit,
            has_more=len(window) > query.limit,
        )

    def unread_count(self, user_id: uuid.UUID) -> int:
        """Return the badge count on its own, for clients that want it without a page."""
        return self._repository.count_unread(user_id)

    def mark_read(
        self,
        notification_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        at: datetime | None = None,
    ) -> Notification:
        """Mark one of ``user_id``'s notifications read and return it.

        Owner-scoped and idempotent. A second call is not merely tolerated but *cheap*: the
        entity reports that it is already read, so no write is issued at all and the original
        ``read_at`` cannot drift -- which matters because this is a client-driven endpoint and
        a double-tap on a phone is an ordinary event, not an edge case.

        Raises :class:`~app.domain.errors.NotificationNotFound` when the notification is
        unknown, expired, or someone else's -- three situations the store deliberately makes
        indistinguishable.
        """
        existing = self._repository.get(notification_id, user_id=user_id)
        if existing is None:
            raise NotificationNotFound(f"notification {notification_id} is not available")

        read = existing.mark_read(at=at)
        if read is existing:
            return existing

        stored = self._repository.update(read)
        if stored is None:
            # The record aged out between the read and the write. Reporting it as gone is
            # honest; resurrecting it would put an expired notification back in the feed.
            raise NotificationNotFound(f"notification {notification_id} is no longer available")
        return stored
