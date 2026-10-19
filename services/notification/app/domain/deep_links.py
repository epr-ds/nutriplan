"""Deep links into the app's screens (NTF-304).

One scheme, one spelling of each route. The mobile router parses exactly these strings
(``Route.fromDeepLink`` / ``Route.fromNotificationData``, NTF-508), and a notification's
``payload["deepLink"]`` and the push ``data["deepLink"]`` are the same value, so a second
hand-built URL anywhere would be a second contract.

Path segments are percent-encoded: the mobile plan parser splits on ``/`` and rejects a
third segment, so an id containing a slash must arrive as one segment. UUIDs are unchanged
by encoding, which is what every producer currently sends.
"""

from __future__ import annotations

from urllib.parse import quote

SCHEME = "nutriplan"


def order_deep_link(order_id: str) -> str:
    """The order detail / tracking screen."""
    return f"{SCHEME}://order/{_segment(order_id)}"


def plan_deep_link(plan_id: str, action: str | None = None) -> str:
    """The plan screen, optionally at a sub-path such as ``manage``, ``summary`` or ``renew``."""
    link = f"{SCHEME}://plan/{_segment(plan_id)}"
    return f"{link}/{_segment(action)}" if action else link


def meal_deep_link(meal_id: str) -> str:
    """The meal detail screen."""
    return f"{SCHEME}://meal/{_segment(meal_id)}"


def _segment(value: str) -> str:
    return quote(value, safe="")
