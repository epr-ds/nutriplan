"""NTF-105 feed use-case tests, run against **both** store adapters.

Everything here goes through the ``repository`` fixture, so each test is a contract the
in-memory and Redis stores must both satisfy. That matters more for this story than for most:
the feed's paging, ordering, and unread accounting are the properties a user actually sees,
and an in-memory store that paged differently from Redis would make the whole suite a fiction.

Times are anchored to a *recent* moment rather than a fixed calendar date, because the test
retention policy is an hour wide -- a hard-coded 2026 timestamp would fall outside it and
every record would be dropped on write.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.application.feed import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    FeedQuery,
    NotificationFeed,
)
from app.domain.enums import NotificationType
from app.domain.errors import InvalidFeedQuery, NotificationNotFound
from app.domain.notification import Notification
from app.domain.repositories import NotificationRepository

NOW = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=30)
USER = uuid.uuid4()
OTHER_USER = uuid.uuid4()


def _notification(
    *,
    user_id: uuid.UUID = USER,
    age_seconds: int = 0,
    read: bool = False,
    type_: NotificationType = NotificationType.ORDER_CONFIRMED,
) -> Notification:
    created = NOW - timedelta(seconds=age_seconds)
    return Notification(
        user_id=user_id,
        type=type_,
        payload={"orderId": str(uuid.uuid4())},
        created_at=created,
        read_at=created if read else None,
    )


def _seed(repository: NotificationRepository, *notifications: Notification) -> None:
    for notification in notifications:
        repository.add(notification)


@pytest.fixture
def feed(repository: NotificationRepository) -> NotificationFeed:
    return NotificationFeed(repository)


# -- query validation ------------------------------------------------------------------


def test_a_feed_query_defaults_to_the_first_page():
    query = FeedQuery(user_id=USER)
    assert (query.page, query.limit, query.offset, query.unread_only) == (
        1,
        DEFAULT_PAGE_SIZE,
        0,
        False,
    )


@pytest.mark.parametrize(("page", "limit", "expected"), [(1, 20, 0), (2, 20, 20), (4, 5, 15)])
def test_a_feed_query_converts_pages_into_store_offsets(page, limit, expected):
    assert FeedQuery(user_id=USER, page=page, limit=limit).offset == expected


@pytest.mark.parametrize("page", [0, -1])
def test_a_feed_query_rejects_a_page_below_one(page):
    with pytest.raises(InvalidFeedQuery):
        FeedQuery(user_id=USER, page=page)


@pytest.mark.parametrize("limit", [0, -5])
def test_a_feed_query_rejects_a_non_positive_limit(limit):
    with pytest.raises(InvalidFeedQuery):
        FeedQuery(user_id=USER, limit=limit)


def test_a_feed_query_rejects_a_limit_above_the_cap():
    """One request must not be able to materialize a user's whole retained feed: the cost of
    that lands on the Redis every other request shares."""
    with pytest.raises(InvalidFeedQuery):
        FeedQuery(user_id=USER, limit=MAX_PAGE_SIZE + 1)


def test_a_feed_query_accepts_the_cap_itself():
    assert FeedQuery(user_id=USER, limit=MAX_PAGE_SIZE).limit == MAX_PAGE_SIZE


# -- listing ---------------------------------------------------------------------------


def test_an_empty_feed_is_an_empty_page(feed: NotificationFeed):
    page = feed.page(FeedQuery(user_id=USER))
    assert page.items == ()
    assert page.unread_count == 0
    assert page.has_more is False
    assert len(page) == 0


def test_the_feed_is_ordered_newest_first(feed: NotificationFeed):
    oldest = _notification(age_seconds=300)
    middle = _notification(age_seconds=200)
    newest = _notification(age_seconds=100)
    _seed(feed.repository, oldest, newest, middle)

    page = feed.page(FeedQuery(user_id=USER))

    assert [item.id for item in page.items] == [newest.id, middle.id, oldest.id]


def test_pages_are_disjoint_and_cover_the_feed(feed: NotificationFeed):
    notifications = [_notification(age_seconds=index * 10) for index in range(5)]
    _seed(feed.repository, *notifications)

    first = feed.page(FeedQuery(user_id=USER, page=1, limit=2))
    second = feed.page(FeedQuery(user_id=USER, page=2, limit=2))
    third = feed.page(FeedQuery(user_id=USER, page=3, limit=2))

    seen = [item.id for item in first.items + second.items + third.items]
    assert seen == [n.id for n in notifications]
    assert len(set(seen)) == 5


def test_has_more_is_true_while_further_entries_exist(feed: NotificationFeed):
    _seed(feed.repository, *(_notification(age_seconds=i * 10) for i in range(5)))

    assert feed.page(FeedQuery(user_id=USER, page=1, limit=2)).has_more is True


def test_has_more_is_false_on_the_last_partial_page(feed: NotificationFeed):
    _seed(feed.repository, *(_notification(age_seconds=i * 10) for i in range(5)))

    assert feed.page(FeedQuery(user_id=USER, page=3, limit=2)).has_more is False


def test_has_more_is_false_when_the_last_page_is_exactly_full(feed: NotificationFeed):
    """The interesting case for the over-fetch: four entries paged two at a time ends on a
    *full* page, and a client that inferred "full page means more" would request an empty
    one. Asking for one extra row is what lets the answer be truthful here."""
    _seed(feed.repository, *(_notification(age_seconds=i * 10) for i in range(4)))

    second = feed.page(FeedQuery(user_id=USER, page=2, limit=2))

    assert len(second) == 2
    assert second.has_more is False


def test_a_page_past_the_end_is_empty(feed: NotificationFeed):
    _seed(feed.repository, _notification())

    page = feed.page(FeedQuery(user_id=USER, page=5, limit=10))

    assert page.items == ()
    assert page.has_more is False


def test_a_page_echoes_the_requested_bounds(feed: NotificationFeed):
    page = feed.page(FeedQuery(user_id=USER, page=3, limit=7))
    assert (page.page, page.limit) == (3, 7)


def test_the_feed_never_shows_another_users_notifications(feed: NotificationFeed):
    mine = _notification()
    theirs = _notification(user_id=OTHER_USER)
    _seed(feed.repository, mine, theirs)

    page = feed.page(FeedQuery(user_id=USER))

    assert [item.id for item in page.items] == [mine.id]


def test_unread_only_pages_the_unread_index(feed: NotificationFeed):
    unread = _notification(age_seconds=10)
    read = _notification(age_seconds=20, read=True)
    _seed(feed.repository, unread, read)

    page = feed.page(FeedQuery(user_id=USER, unread_only=True))

    assert [item.id for item in page.items] == [unread.id]


def test_unread_only_does_not_change_the_badge(feed: NotificationFeed):
    """``unreadCount`` is the badge for the whole feed, not a total of the page -- so a
    filtered request and an unfiltered one must report the same number."""
    _seed(feed.repository, _notification(age_seconds=10), _notification(age_seconds=20, read=True))

    filtered = feed.page(FeedQuery(user_id=USER, unread_only=True))
    unfiltered = feed.page(FeedQuery(user_id=USER))

    assert filtered.unread_count == unfiltered.unread_count == 1


# -- unread count ----------------------------------------------------------------------


def test_the_unread_count_starts_at_zero(feed: NotificationFeed):
    assert feed.unread_count(USER) == 0


def test_the_unread_count_excludes_already_read_notifications(feed: NotificationFeed):
    _seed(
        feed.repository,
        _notification(age_seconds=10),
        _notification(age_seconds=20),
        _notification(age_seconds=30, read=True),
    )

    assert feed.unread_count(USER) == 2


def test_the_unread_count_is_per_user(feed: NotificationFeed):
    _seed(feed.repository, _notification(), _notification(user_id=OTHER_USER))

    assert feed.unread_count(USER) == 1
    assert feed.unread_count(OTHER_USER) == 1


# -- mark read -------------------------------------------------------------------------


def test_marking_read_records_the_moment(feed: NotificationFeed):
    notification = _notification()
    _seed(feed.repository, notification)

    read = feed.mark_read(notification.id, user_id=USER)

    assert read.is_read is True
    assert read.read_at is not None


def test_marking_read_persists(feed: NotificationFeed):
    """The state change has to survive the round trip -- AC2 is about *persisted* read-state,
    not about the object the call happened to return."""
    notification = _notification()
    _seed(feed.repository, notification)

    feed.mark_read(notification.id, user_id=USER)
    stored = feed.repository.get(notification.id, user_id=USER)

    assert stored is not None
    assert stored.is_read is True


def test_marking_read_drops_it_out_of_the_unread_count(feed: NotificationFeed):
    first = _notification(age_seconds=10)
    _seed(feed.repository, first, _notification(age_seconds=20))
    assert feed.unread_count(USER) == 2

    feed.mark_read(first.id, user_id=USER)

    assert feed.unread_count(USER) == 1


def test_marking_read_drops_it_out_of_the_unread_page(feed: NotificationFeed):
    notification = _notification()
    _seed(feed.repository, notification)

    feed.mark_read(notification.id, user_id=USER)

    assert feed.page(FeedQuery(user_id=USER, unread_only=True)).items == ()


def test_marking_read_keeps_it_in_the_main_feed(feed: NotificationFeed):
    """Reading a notification is not deleting it: it stays in the feed, just no longer bold."""
    notification = _notification()
    _seed(feed.repository, notification)

    feed.mark_read(notification.id, user_id=USER)
    page = feed.page(FeedQuery(user_id=USER))

    assert [item.id for item in page.items] == [notification.id]
    assert page.items[0].is_read is True


def test_marking_read_twice_does_not_move_the_timestamp(feed: NotificationFeed):
    """A double-tap on a phone is ordinary, not an edge case. The second call must be a
    no-op rather than a silent rewrite of when the user first saw the notification."""
    notification = _notification()
    _seed(feed.repository, notification)

    first = feed.mark_read(notification.id, user_id=USER)
    second = feed.mark_read(notification.id, user_id=USER)

    assert second.read_at == first.read_at


def test_marking_read_at_an_explicit_moment(feed: NotificationFeed):
    notification = _notification(age_seconds=60)
    _seed(feed.repository, notification)
    moment = NOW - timedelta(seconds=30)

    read = feed.mark_read(notification.id, user_id=USER, at=moment)

    assert read.read_at == moment


def test_marking_an_unknown_notification_read_is_not_found(feed: NotificationFeed):
    with pytest.raises(NotificationNotFound):
        feed.mark_read(uuid.uuid4(), user_id=USER)


def test_marking_another_users_notification_read_is_not_found(feed: NotificationFeed):
    """Indistinguishable from an unknown id on purpose: a different answer here would let a
    caller enumerate UUIDs and learn which ones are real notifications belonging to others."""
    theirs = _notification(user_id=OTHER_USER)
    _seed(feed.repository, theirs)

    with pytest.raises(NotificationNotFound):
        feed.mark_read(theirs.id, user_id=USER)


def test_marking_another_users_notification_read_does_not_touch_it(feed: NotificationFeed):
    theirs = _notification(user_id=OTHER_USER)
    _seed(feed.repository, theirs)

    with pytest.raises(NotificationNotFound):
        feed.mark_read(theirs.id, user_id=USER)

    stored = feed.repository.get(theirs.id, user_id=OTHER_USER)
    assert stored is not None
    assert stored.is_read is False
    assert feed.unread_count(OTHER_USER) == 1


def test_read_state_is_tracked_per_user(feed: NotificationFeed):
    """AC2 in its sharpest form: two users, one notification each, one of them reads theirs.
    The other's badge must not move."""
    mine = _notification()
    theirs = _notification(user_id=OTHER_USER)
    _seed(feed.repository, mine, theirs)

    feed.mark_read(mine.id, user_id=USER)

    assert feed.unread_count(USER) == 0
    assert feed.unread_count(OTHER_USER) == 1
