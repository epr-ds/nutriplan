"""Notification preferences router (NTF-104): read and replace the caller's settings.

Two endpoints, both owner-scoped by the token subject and never by a request parameter -- the
same rule the feed follows, for the same reason: there is no request a client can make that
reads or writes somebody else's preferences.

Route order matters again. ``/notifications/preferences`` is a literal segment that would
otherwise be captured by ``/notifications/{notification_id}/read``'s parameter, so this router
is included **before** the feed router in :mod:`app.main`.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUserId, PreferenceServiceDep
from app.api.schemas import (
    NotificationPreferencesResponse,
    UpdateNotificationPreferencesRequest,
)

router = APIRouter(tags=["Notifications"])


@router.get(
    "/notifications/preferences",
    response_model=NotificationPreferencesResponse,
    summary="Get the current user's notification preferences",
)
def get_preferences(
    user_id: CurrentUserId,
    preferences: PreferenceServiceDep,
) -> NotificationPreferencesResponse:
    """Return the caller's complete preference matrix.

    Every notification type is listed, whether or not the user has ever changed it, so a
    client can render the settings screen without knowing the catalogue in advance. A user
    who has never saved anything gets the defaults -- everything enabled, no quiet hours --
    rather than a ``404``: they do have preferences, they simply have not changed any.
    """
    return NotificationPreferencesResponse.from_domain(preferences.get(user_id))


@router.put(
    "/notifications/preferences",
    response_model=NotificationPreferencesResponse,
    status_code=status.HTTP_200_OK,
    summary="Replace the current user's notification preferences",
)
def replace_preferences(
    user_id: CurrentUserId,
    request: UpdateNotificationPreferencesRequest,
    preferences: PreferenceServiceDep,
) -> NotificationPreferencesResponse:
    """Replace the caller's preferences wholesale and return the stored result.

    This is a replacement, not a patch: a type omitted from ``types`` returns to its default
    (enabled on every channel) and a ``quietHours`` of ``null`` clears the window. Listing the
    same type twice is rejected with ``422`` rather than resolved last-wins, since two rows
    for one type carry two different answers to the same question.

    Quiet hours suppress **push only**. The in-app feed is pull-based and silent, so
    withholding an entry from it overnight would spare the user nothing and would either
    surface the notification out of order in the morning or lose it outright.
    """
    matrix = preferences.replace(
        user_id,
        types=[row.to_domain() for row in request.types],
        quiet_hours=None if request.quiet_hours is None else request.quiet_hours.to_domain(),
    )
    return NotificationPreferencesResponse.from_domain(matrix)
