"""The retention policy (AC2), checked as behaviour rather than as configuration.

The feed is a rolling window bounded two ways -- by age and by count -- and both bounds have
to hold in *both* stores, so the behavioural tests here take the parametrized ``repository``
fixture like the rest of the contract.

Age is exercised by writing notifications whose ``created_at`` is already outside the
window, rather than by sleeping: the index score *is* the creation time, so a notification
"created" two hours ago is indistinguishable from one that has been sitting there for two
hours. The Redis-only tests below then confirm the mechanics the behaviour rests on -- that
a real ``EX`` is set, and that an index entry pointing at a vanished record is survivable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.adapters.keys import NotificationKeys
from app.adapters.retention import RetentionPolicy
from app.domain.enums import NotificationType
from app.domain.notification import Notification
from app.domain.repositories import NotificationRepository
from tests.conftest import TEST_POLICY, drop_namespace, isolated_namespace, redis_repository

NOW = datetime.now(UTC).replace(microsecond=0)
INSIDE = NOW - timedelta(minutes=5)
OUTSIDE = NOW - timedelta(seconds=TEST_POLICY.ttl_seconds + 600)


def _notification(user_id: uuid.UUID, created_at: datetime, **overrides: object) -> Notification:
    defaults: dict[str, object] = {
        "user_id": user_id,
        "type": NotificationType.MEAL_REMINDER,
        "created_at": created_at,
    }
    return Notification(**(defaults | overrides))  # type: ignore[arg-type]


# -- behaviour, on both stores ---------------------------------------------------


def test_adding_an_already_aged_out_notification_is_a_no_op(
    repository: NotificationRepository,
) -> None:
    # NTF-201 must tolerate replayed events. Re-delivering one from outside the window must
    # not resurrect it -- a store that leased from *write* time would put a months-old
    # notification back at the top of the feed with a full fresh lifetime.
    user = uuid.uuid4()
    stale = repository.add(_notification(user, OUTSIDE))
    fresh = repository.add(_notification(user, INSIDE))

    assert repository.get(stale.id, user_id=user) is None
    assert [n.id for n in repository.list_for_user(user)] == [fresh.id]
    assert repository.count_unread(user) == 1


def test_an_aged_out_notification_is_no_longer_readable(
    repository: NotificationRepository,
) -> None:
    user = uuid.uuid4()
    stale = repository.add(_notification(user, OUTSIDE))

    assert repository.get(stale.id, user_id=user) is None


def test_an_aged_out_notification_is_not_in_the_feed(
    repository: NotificationRepository,
) -> None:
    user = uuid.uuid4()
    repository.add(_notification(user, OUTSIDE))
    fresh = repository.add(_notification(user, INSIDE))

    assert [n.id for n in repository.list_for_user(user)] == [fresh.id]


def test_an_aged_out_notification_is_not_counted_as_unread(
    repository: NotificationRepository,
) -> None:
    # The badge must not drift upward forever as old unread entries age out.
    user = uuid.uuid4()
    repository.add(_notification(user, OUTSIDE))

    assert repository.count_unread(user) == 0


def test_the_unread_view_excludes_aged_out_entries(
    repository: NotificationRepository,
) -> None:
    user = uuid.uuid4()
    repository.add(_notification(user, OUTSIDE))
    fresh = repository.add(_notification(user, INSIDE))

    assert [n.id for n in repository.list_for_user(user, unread_only=True)] == [fresh.id]


def test_a_busy_user_s_feed_is_capped(repository: NotificationRepository) -> None:
    # Age alone is not enough: one busy account could grow an unbounded index inside it.
    user = uuid.uuid4()
    for index in range(TEST_POLICY.max_entries + 10):
        repository.add(_notification(user, INSIDE + timedelta(seconds=index)))

    assert repository.count_unread(user) == TEST_POLICY.max_entries
    assert len(repository.list_for_user(user, limit=1_000)) == TEST_POLICY.max_entries


def test_the_cap_keeps_the_newest_notifications(repository: NotificationRepository) -> None:
    user = uuid.uuid4()
    added = [
        repository.add(_notification(user, INSIDE + timedelta(seconds=index)))
        for index in range(TEST_POLICY.max_entries + 5)
    ]

    feed = repository.list_for_user(user, limit=1_000)

    assert [n.id for n in feed] == [n.id for n in reversed(added[5:])]


# -- the in-memory store's own clock ---------------------------------------------


def test_the_in_memory_store_expires_against_its_injected_clock() -> None:
    now = [1_000.0]
    store = InMemoryNotificationRepository(
        policy=RetentionPolicy(ttl_seconds=60, max_entries=10),
        clock=lambda: now[0],
    )
    user = uuid.uuid4()
    created = datetime.fromtimestamp(now[0], tz=UTC)
    notification = store.add(_notification(user, created))

    assert store.get(notification.id, user_id=user) is not None

    now[0] += 61  # travel past the window without sleeping

    assert store.get(notification.id, user_id=user) is None
    assert store.list_for_user(user) == []
    assert store.count_unread(user) == 0


def test_a_policy_without_a_ttl_keeps_everything() -> None:
    now = [1_000.0]
    store = InMemoryNotificationRepository(
        policy=RetentionPolicy(ttl_seconds=0, max_entries=0),
        clock=lambda: now[0],
    )
    user = uuid.uuid4()
    store.add(_notification(user, datetime.fromtimestamp(now[0], tz=UTC)))

    now[0] += 10_000_000

    assert len(store.list_for_user(user)) == 1


# -- the policy value object -----------------------------------------------------


def test_the_horizon_is_one_window_behind_now() -> None:
    assert RetentionPolicy(ttl_seconds=60).horizon(1_000.0) == 940.0


@pytest.mark.parametrize(
    ("created_at", "expired"),
    [(939.0, True), (940.0, True), (941.0, False)],
)
def test_the_window_boundary_is_exclusive(created_at: float, expired: bool) -> None:
    policy = RetentionPolicy(ttl_seconds=60)

    assert policy.is_expired(created_at, now=1_000.0) is expired


def test_a_non_positive_ttl_means_no_expiry() -> None:
    policy = RetentionPolicy(ttl_seconds=0)

    assert policy.expires is False
    assert policy.is_expired(0.0, now=1e9) is False


def test_a_non_positive_cap_means_no_length_bound() -> None:
    assert RetentionPolicy(max_entries=0).bounded is False


# -- Redis mechanics -------------------------------------------------------------


def test_redis_leases_a_record_from_its_creation_not_from_the_write(
    redis_client: object,
) -> None:
    # A notification already half-way through the window gets the *remaining* half, so
    # re-writing it (a replayed event, a read-state change) never extends its life.
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    store = redis_repository(redis_client, namespace=namespace)
    user = uuid.uuid4()
    half = TEST_POLICY.ttl_seconds // 2
    try:
        notification = store.add(_notification(user, NOW - timedelta(seconds=half)))

        ttl = redis_client.ttl(keys.record(notification.id))  # type: ignore[attr-defined]

        assert half - 60 <= ttl <= half + 10
    finally:
        drop_namespace(redis_client, namespace)


def test_redis_sets_a_real_ttl_on_the_record_and_the_indexes(redis_client: object) -> None:
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    store = redis_repository(redis_client, namespace=namespace)
    user = uuid.uuid4()
    try:
        notification = store.add(_notification(user, INSIDE))

        for key in (keys.record(notification.id), keys.feed(user), keys.unread(user)):
            ttl = redis_client.ttl(key)  # type: ignore[attr-defined]
            assert 0 < ttl <= TEST_POLICY.ttl_seconds, key
    finally:
        drop_namespace(redis_client, namespace)


def test_redis_writes_the_record_and_both_index_entries_together(
    redis_client: object,
) -> None:
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    store = redis_repository(redis_client, namespace=namespace)
    user = uuid.uuid4()
    try:
        notification = store.add(_notification(user, INSIDE))

        assert redis_client.exists(keys.record(notification.id)) == 1  # type: ignore[attr-defined]
        assert redis_client.zscore(keys.feed(user), str(notification.id)) is not None  # type: ignore[attr-defined]
        assert redis_client.zscore(keys.unread(user), str(notification.id)) is not None  # type: ignore[attr-defined]
    finally:
        drop_namespace(redis_client, namespace)


def test_redis_marks_read_by_leaving_the_feed_and_dropping_the_unread_entry(
    redis_client: object,
) -> None:
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    store = redis_repository(redis_client, namespace=namespace)
    user = uuid.uuid4()
    try:
        notification = store.add(_notification(user, INSIDE))
        store.update(notification.mark_read(at=NOW))

        assert redis_client.zscore(keys.feed(user), str(notification.id)) is not None  # type: ignore[attr-defined]
        assert redis_client.zscore(keys.unread(user), str(notification.id)) is None  # type: ignore[attr-defined]
    finally:
        drop_namespace(redis_client, namespace)


def test_redis_survives_an_index_entry_whose_record_has_expired(
    redis_client: object,
) -> None:
    # A sorted-set member cannot carry a TTL, so this state is reachable in production.
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    store = redis_repository(redis_client, namespace=namespace)
    user = uuid.uuid4()
    try:
        vanished = store.add(_notification(user, INSIDE))
        survivor = store.add(_notification(user, INSIDE - timedelta(minutes=1)))
        redis_client.delete(keys.record(vanished.id))  # type: ignore[attr-defined]

        feed = store.list_for_user(user)

        assert [n.id for n in feed] == [survivor.id]
        assert redis_client.zscore(keys.feed(user), str(vanished.id)) is None  # type: ignore[attr-defined]
        assert redis_client.zscore(keys.unread(user), str(vanished.id)) is None  # type: ignore[attr-defined]
    finally:
        drop_namespace(redis_client, namespace)


def test_redis_will_not_resurrect_an_expired_record_on_update(
    redis_client: object,
) -> None:
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    store = redis_repository(redis_client, namespace=namespace)
    user = uuid.uuid4()
    try:
        notification = store.add(_notification(user, INSIDE))
        redis_client.delete(keys.record(notification.id))  # type: ignore[attr-defined]

        assert store.update(notification.mark_read(at=NOW)) is None
        assert redis_client.exists(keys.record(notification.id)) == 0  # type: ignore[attr-defined]
    finally:
        drop_namespace(redis_client, namespace)
