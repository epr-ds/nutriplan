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

from app.adapters import codec, preferences_codec
from app.application.feed import FeedPage
from app.application.preferences import PreferenceMatrix, TypePreference
from app.domain.enums import DeliveryStatus, NotificationChannel, NotificationType
from app.domain.notification import Notification
from app.domain.quiet_hours import DEFAULT_TIME_ZONE, QuietHours


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


_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
"""``HH:MM`` in 24-hour local wall-clock time.

Deliberately not OpenAPI's ``format: time``, which is RFC 3339 ``full-time`` and *requires* an
offset (``22:00:00-06:00``). An offset is exactly what this field must not carry: quiet hours
are stored as a local wall-clock time plus an IANA zone name so that the window keeps meaning
"ten at night" across a daylight-saving change, instead of silently shifting by an hour twice
a year. A pattern says what is actually accepted; ``format: time`` would say something else.
"""


class QuietHoursSchema(_Camel):
    """A recurring nightly window, in the user's own local time, during which push is withheld."""

    start: str = Field(pattern=_TIME_PATTERN, examples=["22:00"])
    end: str = Field(pattern=_TIME_PATTERN, examples=["07:00"])
    time_zone: str = Field(
        default=DEFAULT_TIME_ZONE,
        examples=["America/Mexico_City"],
        description="IANA time zone name. An offset is not accepted; see the field pattern.",
    )

    @classmethod
    def from_domain(cls, quiet_hours: QuietHours) -> QuietHoursSchema:
        return cls(
            start=preferences_codec.format_time(quiet_hours.start),
            end=preferences_codec.format_time(quiet_hours.end),
            time_zone=quiet_hours.time_zone,
        )

    def to_domain(self) -> QuietHours:
        """Build the domain window, letting it own the validation the pattern cannot express.

        The regex proves the strings are times; it cannot know whether the zone exists or
        whether ``start`` and ``end`` differ. Both are :class:`InvalidPreferences`, rendered
        as ``422`` -- the same status a pattern violation produces, so a client sees one
        consistent answer to "that window is not acceptable".
        """
        return QuietHours(
            start=preferences_codec.parse_time(self.start, name="quietHours.start"),
            end=preferences_codec.parse_time(self.end, name="quietHours.end"),
            time_zone=self.time_zone,
        )


class TypePreferenceSchema(_Camel):
    """One row of the preference matrix: a notification type and its per-channel switches."""

    type: NotificationType
    in_app: bool = True
    push: bool = True

    @classmethod
    def from_domain(cls, row: TypePreference) -> TypePreferenceSchema:
        return cls(type=row.type, in_app=row.in_app, push=row.push)

    def to_domain(self) -> TypePreference:
        return TypePreference(type=self.type, in_app=self.in_app, push=self.push)


class NotificationPreferencesResponse(_Camel):
    """A user's complete preference matrix.

    ``types`` is an **array of rows**, not an object keyed by type. A map would be shorter on
    the wire and worse everywhere else: OpenAPI can only describe it as free-form
    ``additionalProperties``, so no generated client gets a typed accessor or an exhaustive
    switch; key order is not guaranteed, so a settings screen would have to impose one; and
    the array renders directly as the list the user is looking at. Rows arrive in
    ``NotificationType`` declaration order, which groups the order-lifecycle types together.
    """

    types: list[TypePreferenceSchema]
    quiet_hours: QuietHoursSchema | None = None
    updated_at: datetime

    @classmethod
    def from_domain(cls, matrix: PreferenceMatrix) -> NotificationPreferencesResponse:
        return cls(
            types=[TypePreferenceSchema.from_domain(row) for row in matrix.types],
            quiet_hours=(
                None
                if matrix.quiet_hours is None
                else QuietHoursSchema.from_domain(matrix.quiet_hours)
            ),
            updated_at=matrix.updated_at,
        )


class UpdateNotificationPreferencesRequest(_Camel):
    """A full replacement of the caller's preferences.

    Any type left out of ``types`` returns to its default (enabled on every channel), and a
    ``quietHours`` of ``null`` clears the window. See
    :mod:`app.application.preferences` for why this is a replacement rather than a patch.

    ``types`` is **required**, with no default. Since omitting a row resets it, a defaulted
    ``types`` would turn a client that forgot the field -- one sending only ``quietHours``,
    say -- into a request that silently switches every notification back on. Requiring it
    makes that a ``422`` instead. A client that really does want the defaults sends ``[]``.
    """

    types: list[TypePreferenceSchema]
    quiet_hours: QuietHoursSchema | None = None
