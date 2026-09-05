"""The notification store contract -- run against **both** adapters.

Every test here takes the parametrized ``repository`` fixture, so each one executes twice:
once against the in-process store and once against real Redis (skipped locally, required in
CI). That is the point of the suite. An in-memory stand-in that is only checked against
itself proves nothing about production; holding both to the same expectations is what makes
"passes the tests" mean "will behave in production".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.enums import DeliveryStatus, NotificationChannel, NotificationType
from app.domain.notification import Notification
from app.domain.repositories import NotificationRepository

NOW = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=30)
"""Anchored to real time, comfortably inside the harness retention window.

A fixed calendar constant would be correct today and silently outside the window tomorrow,
turning every store test into a failure that looks like a retention bug.
"""


def _user() -> uuid.UUID:
    return uuid.uuid4()


def _notification(user_id: uuid.UUID, *, minutes: int = 0, **overrides: object) -> Notification:
    defaults: dict[str, object] = {
        "user_id": user_id,
        "type": NotificationType.ORDER_CONFIRMED,
        "created_at": NOW + timedelta(minutes=minutes),
        "payload": {"orderId": "abc"},
    }
    return Notification(**(defaults | overrides))  # type: ignore[arg-type]


# -- add / get -------------------------------------------------------------------


def test_a_stored_notification_can_be_read_back(repository: NotificationRepository) -> None:
    user = _user()
    notification = _notification(user, payload={"orderId": "abc", "eta": {"minutes": 12}})

    repository.add(notification)

    assert repository.get(notification.id, user_id=user) == notification


def test_add_returns_the_notification_it_stored(repository: NotificationRepository) -> None:
    user = _user()
    notification = _notification(user)

    assert repository.add(notification) == notification


def test_an_unknown_id_is_absent(repository: NotificationRepository) -> None:
    assert repository.get(uuid.uuid4(), user_id=_user()) is None


def test_another_user_s_notification_is_indistinguishable_from_an_unknown_one(
    repository: NotificationRepository,
) -> None:
    # Owner-scoping is what stops the feed API leaking by enumerating UUIDs.
    owner, intruder = _user(), _user()
    notification = repository.add(_notification(owner))

    assert repository.get(notification.id, user_id=intruder) is None


def test_re_adding_the_same_id_overwrites_rather_than_duplicates(
    repository: NotificationRepository,
) -> None:
    user = _user()
    notification = repository.add(_notification(user))

    repository.add(notification.with_status(DeliveryStatus.DELIVERED))

    assert repository.get(notification.id, user_id=user).status is DeliveryStatus.DELIVERED
    assert len(repository.list_for_user(user)) == 1


def test_every_field_survives_the_store(repository: NotificationRepository) -> None:
    user = _user()
    notification = _notification(
        user,
        type=NotificationType.PLAN_ENDING,
        channels=(NotificationChannel.PUSH, NotificationChannel.IN_APP),
        status=DeliveryStatus.SENT,
        read_at=NOW + timedelta(minutes=1),
        payload={"planId": "p1", "days": [1, 2, 3], "nested": {"deep": True}},
    )

    repository.add(notification)
    loaded = repository.get(notification.id, user_id=user)

    assert loaded == notification
    assert loaded.channels == (NotificationChannel.PUSH, NotificationChannel.IN_APP)
    assert loaded.payload["nested"]["deep"] is True
    assert loaded.payload["days"] == (1, 2, 3)


# -- per-user feed (AC3) ---------------------------------------------------------


def test_the_feed_is_newest_first(repository: NotificationRepository) -> None:
    user = _user()
    oldest = repository.add(_notification(user, minutes=0))
    newest = repository.add(_notification(user, minutes=10))
    middle = repository.add(_notification(user, minutes=5))

    feed = repository.list_for_user(user)

    assert [n.id for n in feed] == [newest.id, middle.id, oldest.id]


def test_a_feed_contains_only_its_own_user_s_notifications(
    repository: NotificationRepository,
) -> None:
    mine, theirs = _user(), _user()
    repository.add(_notification(mine))
    repository.add(_notification(theirs))

    assert len(repository.list_for_user(mine)) == 1
    assert len(repository.list_for_user(theirs)) == 1


def test_a_user_with_no_notifications_has_an_empty_feed(
    repository: NotificationRepository,
) -> None:
    assert repository.list_for_user(_user()) == []


def test_the_feed_paginates(repository: NotificationRepository) -> None:
    user = _user()
    added = [repository.add(_notification(user, minutes=index)) for index in range(5)]
    newest_first = [n.id for n in reversed(added)]

    first = repository.list_for_user(user, limit=2)
    second = repository.list_for_user(user, limit=2, offset=2)
    third = repository.list_for_user(user, limit=2, offset=4)

    assert [n.id for n in first] == newest_first[:2]
    assert [n.id for n in second] == newest_first[2:4]
    assert [n.id for n in third] == newest_first[4:]


def test_an_offset_past_the_end_is_empty(repository: NotificationRepository) -> None:
    user = _user()
    repository.add(_notification(user))

    assert repository.list_for_user(user, offset=50) == []


@pytest.mark.parametrize("limit", [0, -1])
def test_a_non_positive_limit_returns_nothing(
    repository: NotificationRepository, limit: int
) -> None:
    user = _user()
    repository.add(_notification(user))

    assert repository.list_for_user(user, limit=limit) == []


def test_notifications_created_in_the_same_instant_are_ordered_stably(
    repository: NotificationRepository,
) -> None:
    # Equal scores must not make pagination lose or repeat an entry.
    user = _user()
    for _ in range(4):
        repository.add(_notification(user, minutes=0))

    first_page = repository.list_for_user(user, limit=2)
    second_page = repository.list_for_user(user, limit=2, offset=2)
    seen = [n.id for n in first_page + second_page]

    assert len(set(seen)) == 4
    assert [n.id for n in repository.list_for_user(user, limit=2)] == [n.id for n in first_page]


# -- unread state ----------------------------------------------------------------


def test_a_new_notification_is_unread(repository: NotificationRepository) -> None:
    user = _user()
    repository.add(_notification(user))

    assert repository.count_unread(user) == 1


def test_a_notification_stored_already_read_does_not_count_as_unread(
    repository: NotificationRepository,
) -> None:
    user = _user()
    repository.add(_notification(user, read_at=NOW))

    assert repository.count_unread(user) == 0
    assert repository.list_for_user(user, unread_only=True) == []


def test_marking_read_clears_it_from_the_unread_view(
    repository: NotificationRepository,
) -> None:
    user = _user()
    unread = repository.add(_notification(user, minutes=1))
    read = repository.add(_notification(user, minutes=0))

    repository.update(read.mark_read(at=NOW + timedelta(minutes=5)))

    assert repository.count_unread(user) == 1
    assert [n.id for n in repository.list_for_user(user, unread_only=True)] == [unread.id]
    assert len(repository.list_for_user(user)) == 2  # still in the full feed


def test_unread_counts_are_per_user(repository: NotificationRepository) -> None:
    mine, theirs = _user(), _user()
    repository.add(_notification(mine))
    repository.add(_notification(theirs))
    repository.add(_notification(theirs, minutes=1))

    assert repository.count_unread(mine) == 1
    assert repository.count_unread(theirs) == 2


def test_a_user_with_nothing_has_no_unread(repository: NotificationRepository) -> None:
    assert repository.count_unread(_user()) == 0


def test_the_unread_view_is_also_newest_first(repository: NotificationRepository) -> None:
    user = _user()
    older = repository.add(_notification(user, minutes=0))
    newer = repository.add(_notification(user, minutes=5))

    assert [n.id for n in repository.list_for_user(user, unread_only=True)] == [
        newer.id,
        older.id,
    ]


# -- update ----------------------------------------------------------------------


def test_update_persists_a_delivery_receipt(repository: NotificationRepository) -> None:
    user = _user()
    notification = repository.add(_notification(user))

    repository.update(notification.with_status(DeliveryStatus.DELIVERED))

    assert repository.get(notification.id, user_id=user).status is DeliveryStatus.DELIVERED


def test_update_returns_the_stored_notification(repository: NotificationRepository) -> None:
    user = _user()
    notification = repository.add(_notification(user))
    read = notification.mark_read(at=NOW + timedelta(minutes=1))

    assert repository.update(read) == read


def test_update_will_not_resurrect_a_notification_that_was_never_stored(
    repository: NotificationRepository,
) -> None:
    # A store that re-created an expired record would make it reappear with a stale date.
    user = _user()

    assert repository.update(_notification(user)) is None
    assert repository.list_for_user(user) == []


def test_marking_read_does_not_move_the_notification_in_the_feed(
    repository: NotificationRepository,
) -> None:
    user = _user()
    older = repository.add(_notification(user, minutes=0))
    newer = repository.add(_notification(user, minutes=5))

    repository.update(older.mark_read(at=NOW + timedelta(hours=1)))

    assert [n.id for n in repository.list_for_user(user)] == [newer.id, older.id]
