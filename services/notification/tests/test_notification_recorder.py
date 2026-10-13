"""Replayed events are no-ops -- the story's headline behaviour (AC3).

These run against the parametrized ``recorder`` fixture, so every expectation holds for the
in-process pair *and* for real Redis. This is the test hook the backlog asks for: a consumer
(NTF-202) proves it handles a redelivery correctly by replaying the same event through
:class:`NotificationRecorder` and asserting the feed is unchanged, exactly as below.

Two failure directions are covered as well as the happy one, because the interesting part of
an idempotent write path is not that it suppresses the second delivery -- it is that it does
so without swallowing notifications when something goes wrong in between.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.idempotency import IdempotencyWindow
from app.adapters.in_memory_deduplication_store import InMemoryDeduplicationStore
from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.application.notification_recorder import NotificationRecorder, RecordResult
from app.domain.enums import NotificationType
from app.domain.errors import InvalidDedupeKey
from app.domain.notification import Notification
from app.domain.repositories import NotificationRepository
from tests.conftest import TEST_POLICY, TEST_WINDOW

NOW = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=30)
"""Anchored to real time so the harness retention window never ages the fixtures out."""

EVENT = "order-evt-9f21"


def _notification(
    user_id: uuid.UUID,
    *,
    notification_type: NotificationType = NotificationType.ORDER_CONFIRMED,
    **overrides: object,
) -> Notification:
    defaults: dict[str, object] = {
        "user_id": user_id,
        "type": notification_type,
        "created_at": NOW,
        "payload": {"orderId": "abc"},
    }
    return Notification(**(defaults | overrides))  # type: ignore[arg-type]


def _in_memory_recorder(
    repository: NotificationRepository | None = None,
) -> NotificationRecorder:
    return NotificationRecorder(
        repository or InMemoryNotificationRepository(policy=TEST_POLICY),
        InMemoryDeduplicationStore(window=TEST_WINDOW),
    )


# -- the happy path --------------------------------------------------------------


def test_a_first_delivery_is_recorded(recorder: NotificationRecorder) -> None:
    user = uuid.uuid4()
    notification = _notification(user)

    result = recorder.record(notification, event_id=EVENT)

    assert result.recorded
    assert not result.duplicate
    assert result.confirmed
    assert result.notification == notification


def test_the_result_is_truthy_when_it_did_the_work(recorder: NotificationRecorder) -> None:
    assert recorder.record(_notification(uuid.uuid4()), event_id=EVENT)


# -- the no-op -------------------------------------------------------------------


def test_replaying_an_event_does_not_store_a_second_notification(
    recorder: NotificationRecorder,
) -> None:
    """The headline: one event, one notification, however many times it is delivered."""
    user = uuid.uuid4()
    first = recorder.record(_notification(user), event_id=EVENT)

    replay = recorder.record(_notification(user), event_id=EVENT)

    assert replay.duplicate
    assert not replay.recorded
    assert recorder.repository.list_for_user(user) == [first.notification]


def test_a_replay_resolves_the_original_notification(
    recorder: NotificationRecorder,
) -> None:
    """A refused delivery reports *what* the user was sent, not merely that it happened."""
    user = uuid.uuid4()
    first = recorder.record(_notification(user), event_id=EVENT)

    replay = recorder.record(_notification(user), event_id=EVENT)

    assert replay.notification == first.notification
    assert replay.notification is not None


def test_many_replays_still_produce_exactly_one_notification(
    recorder: NotificationRecorder,
) -> None:
    user = uuid.uuid4()

    results = [recorder.record(_notification(user), event_id=EVENT) for _ in range(5)]

    assert [r.recorded for r in results] == [True, False, False, False, False]
    assert len(recorder.repository.list_for_user(user)) == 1
    assert recorder.repository.count_unread(user) == 1


def test_a_replay_does_not_disturb_read_state(recorder: NotificationRecorder) -> None:
    """A redelivery must not quietly mark a notification the user already opened unread."""
    user = uuid.uuid4()
    first = recorder.record(_notification(user), event_id=EVENT)
    assert first.notification is not None
    recorder.repository.update(first.notification.mark_read(at=NOW + timedelta(minutes=1)))

    recorder.record(_notification(user), event_id=EVENT)

    stored = recorder.repository.get(first.notification.id, user_id=user)
    assert stored is not None
    assert stored.is_read
    assert recorder.repository.count_unread(user) == 0


# -- what is *not* a duplicate ---------------------------------------------------


def test_the_same_event_for_two_users_notifies_both(recorder: NotificationRecorder) -> None:
    """One order event legitimately reaches everyone party to the order."""
    first_user, second_user = uuid.uuid4(), uuid.uuid4()

    assert recorder.record(_notification(first_user), event_id=EVENT).recorded
    assert recorder.record(_notification(second_user), event_id=EVENT).recorded


def test_the_same_event_may_raise_two_notification_types(
    recorder: NotificationRecorder,
) -> None:
    """A delivered order raises the delivery notice *and* a prompt to rate it."""
    user = uuid.uuid4()

    delivered = recorder.record(
        _notification(user, notification_type=NotificationType.ORDER_DELIVERED),
        event_id=EVENT,
    )
    reminder = recorder.record(
        _notification(user, notification_type=NotificationType.MEAL_REMINDER),
        event_id=EVENT,
    )

    assert delivered.recorded
    assert reminder.recorded
    assert len(recorder.repository.list_for_user(user)) == 2


def test_two_events_of_the_same_type_both_notify(recorder: NotificationRecorder) -> None:
    """Two genuinely distinct orders must not suppress each other."""
    user = uuid.uuid4()

    assert recorder.record(_notification(user), event_id="order-evt-1").recorded
    assert recorder.record(_notification(user), event_id="order-evt-2").recorded
    assert len(recorder.repository.list_for_user(user)) == 2


# -- failure directions ----------------------------------------------------------


class _BrokenRepository(InMemoryNotificationRepository):
    """A store that fails the way a real one does: after being asked, not before."""

    def __init__(self, *, failures: int) -> None:
        super().__init__(policy=TEST_POLICY)
        self.remaining_failures = failures

    def add(self, notification: Notification) -> Notification:
        if self.remaining_failures:
            self.remaining_failures -= 1
            raise ConnectionError("redis is down")
        return super().add(notification)


def test_a_failed_write_releases_the_claim_so_a_retry_succeeds() -> None:
    """An outage must not turn into permanently missing notifications.

    Claiming before writing is what prevents duplicates, but it also means a claim can
    outlive a write that never happened. Releasing on failure is what keeps the next
    redelivery -- likely seconds later -- able to deliver for real.
    """
    repository = _BrokenRepository(failures=1)
    recorder = _in_memory_recorder(repository)
    user = uuid.uuid4()

    with pytest.raises(ConnectionError):
        recorder.record(_notification(user), event_id=EVENT)

    retry = recorder.record(_notification(user), event_id=EVENT)

    assert retry.recorded
    assert len(repository.list_for_user(user)) == 1


def test_a_claim_left_unconfirmed_by_a_crash_lapses() -> None:
    """The provisional lease bounds how long a hard-killed worker can suppress delivery.

    A process killed between claiming and writing never releases anything -- there is no
    ``finally`` that survives ``SIGKILL``. Only the short lease frees the key, and if it did
    not, the redelivered event would be dropped as a duplicate of a notification that was
    never stored.
    """
    now = [1_000.0]
    dedupe = InMemoryDeduplicationStore(
        window=IdempotencyWindow(ttl_seconds=600, provisional_seconds=30),
        clock=lambda: now[0],
    )
    repository = InMemoryNotificationRepository(policy=TEST_POLICY)
    recorder = NotificationRecorder(repository, dedupe)
    user = uuid.uuid4()
    crashed = _notification(user)

    # The worker claims, then dies before the write.
    dedupe.claim(recorder.dedupe_key(crashed, event_id=EVENT), str(crashed.id))
    now[0] += 31.0

    redelivered = recorder.record(_notification(user), event_id=EVENT)

    assert redelivered.recorded
    assert len(repository.list_for_user(user)) == 1


def test_a_confirmed_claim_is_not_freed_by_a_lapsing_provisional_lease() -> None:
    """The mirror of the test above: a completed delivery stays deduplicated."""
    now = [1_000.0]
    dedupe = InMemoryDeduplicationStore(
        window=IdempotencyWindow(ttl_seconds=600, provisional_seconds=30),
        clock=lambda: now[0],
    )
    repository = InMemoryNotificationRepository(policy=TEST_POLICY)
    recorder = NotificationRecorder(repository, dedupe)
    user = uuid.uuid4()
    recorder.record(_notification(user), event_id=EVENT)

    now[0] += 31.0

    assert recorder.record(_notification(user), event_id=EVENT).duplicate
    assert len(repository.list_for_user(user)) == 1


def test_an_unconfirmable_claim_is_reported_rather_than_hidden() -> None:
    """A write slower than its own lease is a misconfiguration worth surfacing."""

    class _LosesTheLease(InMemoryDeduplicationStore):
        def confirm(self, key: object, holder: str) -> bool:
            return False

    recorder = NotificationRecorder(
        InMemoryNotificationRepository(policy=TEST_POLICY),
        _LosesTheLease(window=TEST_WINDOW),
    )

    result = recorder.record(_notification(uuid.uuid4()), event_id=EVENT)

    assert result.recorded
    assert not result.confirmed


def test_a_replay_whose_original_aged_out_is_still_a_no_op() -> None:
    """Dedupe outliving a record is a *decision*, not a bug, so it is pinned here.

    The window is configured well inside the feed's retention so this is rare, but if it
    happens the answer is still "do not write": re-delivering a month-old event would put a
    stale notification at the top of the feed.
    """
    repository = InMemoryNotificationRepository(policy=TEST_POLICY)
    dedupe = InMemoryDeduplicationStore(window=TEST_WINDOW)
    recorder = NotificationRecorder(repository, dedupe)
    user = uuid.uuid4()
    first = recorder.record(_notification(user), event_id=EVENT)
    assert first.notification is not None
    repository._records.pop(str(first.notification.id), None)
    repository._created.pop(str(first.notification.id), None)

    replay = recorder.record(_notification(user), event_id=EVENT)

    assert replay.duplicate
    assert replay.notification is None


def test_a_holder_that_is_not_a_notification_id_resolves_to_nothing() -> None:
    """Robustness at a boundary the store cannot police: the holder is an opaque string."""
    dedupe = InMemoryDeduplicationStore(window=TEST_WINDOW)
    recorder = NotificationRecorder(InMemoryNotificationRepository(policy=TEST_POLICY), dedupe)
    user = uuid.uuid4()
    notification = _notification(user)
    dedupe.claim(recorder.dedupe_key(notification, event_id=EVENT), "not-a-uuid")

    replay = recorder.record(notification, event_id=EVENT)

    assert replay.duplicate
    assert replay.notification is None


# -- the seam consumers use ------------------------------------------------------


def test_the_recorder_exposes_the_key_it_would_use() -> None:
    recorder = _in_memory_recorder()
    notification = _notification(uuid.uuid4())

    key = recorder.dedupe_key(notification, event_id=EVENT)

    assert key.notification_type is NotificationType.ORDER_CONFIRMED
    assert recorder.record(notification, event_id=EVENT).dedupe_key == key


def test_a_blank_event_id_is_rejected_before_anything_is_written() -> None:
    repository = InMemoryNotificationRepository(policy=TEST_POLICY)
    recorder = _in_memory_recorder(repository)
    user = uuid.uuid4()

    with pytest.raises(InvalidDedupeKey):
        recorder.record(_notification(user), event_id="")

    assert repository.list_for_user(user) == []


def test_the_result_names_the_key_it_deduplicated_on(recorder: NotificationRecorder) -> None:
    result = recorder.record(_notification(uuid.uuid4()), event_id=EVENT)

    assert isinstance(result, RecordResult)
    assert str(result.dedupe_key).startswith("order_confirmed:")
