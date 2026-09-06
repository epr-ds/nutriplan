"""In-app notification feed router (NTF-105): list, unread count, mark read.

Three endpoints, all owner-scoped by the token subject and never by a request parameter.

Route order matters here: ``/notifications/unread-count`` is declared before any
``/notifications/{notificationId}`` route so a literal path segment can never be captured as
a UUID path parameter. It costs nothing to get right and is unpleasant to debug when wrong.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserId, NotificationFeedDep
from app.api.schemas import NotificationPageResponse, NotificationResponse, UnreadCountResponse
from app.application.feed import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, FeedQuery

router = APIRouter(tags=["Notifications"])


@router.get(
    "/notifications",
    response_model=NotificationPageResponse,
    summary="List the current user's notifications",
)
def list_notifications(
    user_id: CurrentUserId,
    feed: NotificationFeedDep,
    unread_only: Annotated[bool, Query(alias="unreadOnly")] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> NotificationPageResponse:
    """Return the caller's notifications, newest first, with the unread badge count.

    Results are always scoped to the authenticated caller. ``page`` is 1-based and ``limit``
    is the page size (1-100); out-of-range values are rejected with ``422``. Set
    ``unreadOnly=true`` to page the unread index instead of the full feed -- ``unreadCount``
    is unaffected by the filter, since it is the badge, not a total of the page.

    The feed is a **rolling window, not an archive** (NTF-102): entries age out after the
    configured retention period and each user's index is capped, so a notification that was
    listed last month may legitimately be gone. Use ``hasMore`` to decide whether to request
    the next page rather than inferring it from a full page.
    """
    query = FeedQuery(user_id=user_id, unread_only=unread_only, page=page, limit=limit)
    return NotificationPageResponse.from_domain(feed.page(query))


@router.get(
    "/notifications/unread-count",
    response_model=UnreadCountResponse,
    summary="Count the current user's unread notifications",
)
def unread_count(user_id: CurrentUserId, feed: NotificationFeedDep) -> UnreadCountResponse:
    """Return how many unread notifications the caller has, for the app's badge.

    Separate from the feed because the badge is needed far more often than the list -- on
    launch, on resume, on a push receipt -- and reading a page to count it would transfer
    (and decode) records nobody is going to look at. Only notifications still inside the
    retention window are counted.
    """
    return UnreadCountResponse(unread_count=feed.unread_count(user_id))


@router.post(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark a notification as read",
)
def mark_notification_read(
    notification_id: uuid.UUID,
    user_id: CurrentUserId,
    feed: NotificationFeedDep,
) -> NotificationResponse:
    """Mark one of the caller's notifications read and return its updated state.

    Idempotent: re-reading an already-read notification succeeds and leaves the original
    ``readAt`` untouched, so a double-tap in the app is harmless. Owner-scoped: an unknown
    id, an expired one, and another user's notification are indistinguishable and all yield
    ``404`` (no enumeration). A malformed (non-UUID) id is rejected with ``422``.
    """
    return NotificationResponse.from_domain(feed.mark_read(notification_id, user_id=user_id))
