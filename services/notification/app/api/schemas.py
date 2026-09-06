"""Pydantic response schemas for the in-app feed API (NTF-105).

The wire shape is **not re-derived here**. NTF-102's codec already reduces a notification to
a camelCase JSON record -- that was a deliberate choice at the time ("the stored form is the
wire form") so a record could travel from Redis to a client through one mapping instead of
two. These models reuse it, which means a key renamed in the codec cannot leave the API
publishing the old name: both move together or the projection fails loudly.

Two fields differ from the stored record, and both differences are the point:

* ``userId`` is dropped. The caller is the owner by construction -- the id came from their
  token -- so echoing it back adds nothing and widens the response for no reason.
* ``isRead`` is added. It is derived (``readAt is not None``), but a client that has to know
  that rule is a client that will eventually get it wrong; the response states it outright.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.adapters import codec
from app.application.feed import FeedPage
from app.domain.enums import DeliveryStatus, NotificationChannel, NotificationType
from app.domain.notification import Notification


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class NotificationResponse(_Camel):
    """One notification as the mobile app sees it."""

    id: uuid.UUID
    type: NotificationType
    payload: dict[str, Any] = Field(default_factory=dict)
    channels: list[NotificationChannel]
    status: DeliveryStatus
    created_at: datetime
    read_at: datetime | None = None
    is_read: bool

    @classmethod
    def from_domain(cls, notification: Notification) -> NotificationResponse:
        """Project a stored notification onto the wire form via the store's own codec."""
        record = codec.to_record(notification)
        record.pop("userId")
        record["isRead"] = notification.is_read
        return cls.model_validate(record)


class NotificationPageResponse(_Camel):
    """One page of the feed, plus the badge count.

    ``unreadCount`` rides along on every page so opening the feed refreshes the badge without
    a second request -- the common case by far. It is a snapshot taken alongside the page, not
    a total of the items in it: filtering by ``unreadOnly`` does not change what it counts.
    """

    items: list[NotificationResponse]
    page: int
    limit: int
    unread_count: int
    has_more: bool

    @classmethod
    def from_domain(cls, feed_page: FeedPage) -> NotificationPageResponse:
        return cls(
            items=[NotificationResponse.from_domain(item) for item in feed_page.items],
            page=feed_page.page,
            limit=feed_page.limit,
            unread_count=feed_page.unread_count,
            has_more=feed_page.has_more,
        )


class UnreadCountResponse(_Camel):
    """The badge count on its own, for a client that only needs the number."""

    unread_count: int
