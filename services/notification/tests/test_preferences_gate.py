"""NTF-104 AC1/AC2 at the write path: an opt-out actually stops the notification.

These drive :class:`~app.application.notification_recorder.NotificationRecorder` -- the one
write path event consumers use -- with its preference port wired in. The dedupe store is the
parametrized fixture so the *claim* half runs against a real Redis too, because the sharpest
test here is a negative one: a suppressed notification must leave its dedupe key **free**.

That ordering is not a detail. If the gate ran after the claim, a notification suppressed
today would burn the key, and an NTF-204 dead-letter replay issued tomorrow -- after the user
un-muted the type -- would be refused as a duplicate of a notification that was never written.
The user would simply never learn what happened, and nothing would log an error.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta

import pytest

from app.adapters.in_memory_notification_repository import InMemoryNotificationRepository
from app.adapters.in_memory_preferences_repository import InMemoryPreferencesRepository
from app.application.notification_recorder import NotificationRecorder
from app.domain.enums import DeliveryStatus, NotificationChannel, NotificationType
from app.domain.notification import Notification
from app.domain.preferences import NotificationPreferences
from app.domain.quiet_hours import QuietHours
from tests.conftest import TEST_POLICY

IN_APP = NotificationChannel.IN_APP
PUSH = NotificationChannel.PUSH
CONFIRMED = NotificationType.ORDER_CONFIRMED
DELIVERED = NotificationType.ORDER_DELIVERED

USER = uuid.uuid4()
NIGHT = QuietHours(start=time(22, 0), end=time(7, 0), time_zone="America/Mexico_City")
LATE = datetime(2026, 3, 11, 5, 30, tzinfo=UTC)  # 23:30 in Mexico City
NOON = datetime(2026, 3, 11, 18, 30, tzinfo=UTC)  # 12:30 in Mexico City

NOW = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=30)


def _notification(
    *,
    user_id: uuid.UUID = USER,
    type_: NotificationType = CONFIRMED,
    channels: tuple[NotificationChannel, ...] = (IN_APP, PUSH),
) -> Notification:
    return Notification(
        user_id=user_id,
        type=type_,
        payload={"orderId": "abc"},
        channels=channels,
        status=DeliveryStatus.PENDING,
        created_at=NOW,
    )


class _ExplodingPreferences:
    """A preferences store that is down -- the fail-open case."""

    def get(self, user_id: uuid.UUID) -> NotificationPreferences | None:
        raise RuntimeError("redis is on fire")

    def save(self, preferences: NotificationPreferences) -> NotificationPreferences:
        raise RuntimeError("redis is on fire")


@pytest.fixture
def preferences() -> InMemoryPreferencesRepository:
    return InMemoryPreferencesRepository()


@pytest.fixture
def store(dedupe_store):
    return dedupe_store()


def _recorder(preferences, store, repository=None) -> NotificationRecorder:
    return NotificationRecorder(
        repository or InMemoryNotificationRepository(policy=TEST_POLICY),
        store,
        preferences,
    )


# -- opting out -------------------------------------------------------------------------


def test_a_notification_with_no_preferences_is_recorded_unchanged(preferences, store):
    recorder = _recorder(preferences, store)

    result = recorder.record(_notification(), event_id="evt-1")

    assert result.recorded is True
    assert result.suppressed is False
    assert result.notification is not None
    assert result.notification.channels == (IN_APP, PUSH)


def test_muting_every_channel_suppresses_the_notification_entirely(preferences, store):
    preferences.save(
        NotificationPreferences(user_id=USER).muting(CONFIRMED, PUSH).muting(CONFIRMED, IN_APP)
    )
    repository = InMemoryNotificationRepository(policy=TEST_POLICY)
    recorder = _recorder(preferences, store, repository)

    result = recorder.record(_notification(), event_id="evt-1")

    assert result.suppressed is True
    assert result.recorded is False
    assert bool(result) is False
    assert result.notification is None
    assert set(result.suppressed_channels) == {IN_APP, PUSH}
    assert repository.list_for_user(USER) == []
    assert repository.count_unread(USER) == 0


def test_muting_one_channel_narrows_the_stored_notification(preferences, store):
    preferences.save(NotificationPreferences(user_id=USER).muting(CONFIRMED, PUSH))
    recorder = _recorder(preferences, store)

    result = recorder.record(_notification(), event_id="evt-1")

    assert result.recorded is True
    assert result.notification is not None
    assert result.notification.channels == (IN_APP,)
    assert result.suppressed_channels == (PUSH,)


def test_the_narrowed_channels_are_what_gets_stored(preferences, store):
    """The record itself says push was not used, so nothing downstream re-derives the
    decision against a later clock reading and disagrees with it."""
    preferences.save(NotificationPreferences(user_id=USER).muting(CONFIRMED, PUSH))
    repository = InMemoryNotificationRepository(policy=TEST_POLICY)
    recorder = _recorder(preferences, store, repository)

    stored = recorder.record(_notification(), event_id="evt-1").notification
    assert stored is not None

    read_back = repository.get(stored.id, user_id=USER)
    assert read_back is not None
    assert read_back.channels == (IN_APP,)


def test_a_mute_applies_only_to_the_type_it_names(preferences, store):
    preferences.save(
        NotificationPreferences(user_id=USER).muting(CONFIRMED, PUSH).muting(CONFIRMED, IN_APP)
    )
    recorder = _recorder(preferences, store)

    result = recorder.record(_notification(type_=DELIVERED), event_id="evt-1")

    assert result.recorded is True
    assert result.notification is not None
    assert result.notification.channels == (IN_APP, PUSH)


def test_another_users_mute_does_not_affect_this_one(preferences, store):
    other = uuid.uuid4()
    preferences.save(
        NotificationPreferences(user_id=other).muting(CONFIRMED, PUSH).muting(CONFIRMED, IN_APP)
    )
    recorder = _recorder(preferences, store)

    assert recorder.record(_notification(), event_id="evt-1").recorded is True


# -- quiet hours ------------------------------------------------------------------------


def test_quiet_hours_withhold_push_but_keep_the_feed_entry(preferences, store):
    preferences.save(NotificationPreferences(user_id=USER, quiet_hours=NIGHT))
    recorder = _recorder(preferences, store)

    result = recorder.record(_notification(), event_id="evt-1", at=LATE)

    assert result.recorded is True
    assert result.notification is not None
    assert result.notification.channels == (IN_APP,)
    assert result.suppressed_channels == (PUSH,)


def test_outside_quiet_hours_push_is_kept(preferences, store):
    preferences.save(NotificationPreferences(user_id=USER, quiet_hours=NIGHT))
    recorder = _recorder(preferences, store)

    result = recorder.record(_notification(), event_id="evt-1", at=NOON)

    assert result.notification is not None
    assert result.notification.channels == (IN_APP, PUSH)


def test_a_push_only_notification_is_suppressed_during_quiet_hours(preferences, store):
    """Nothing left to address it to, so nothing is written -- and the key stays free."""
    preferences.save(NotificationPreferences(user_id=USER, quiet_hours=NIGHT))
    repository = InMemoryNotificationRepository(policy=TEST_POLICY)
    recorder = _recorder(preferences, store, repository)

    result = recorder.record(_notification(channels=(PUSH,)), event_id="evt-1", at=LATE)

    assert result.suppressed is True
    assert repository.list_for_user(USER) == []


# -- the ordering that matters ----------------------------------------------------------


def test_a_suppressed_delivery_leaves_the_dedupe_key_free(preferences, store):
    """The whole reason the gate runs before the claim.

    A replay arriving after the user un-mutes must be able to deliver: if the suppressed
    attempt had claimed the key, the replay would be refused as a duplicate of a
    notification that never existed.
    """
    preferences.save(
        NotificationPreferences(user_id=USER).muting(CONFIRMED, PUSH).muting(CONFIRMED, IN_APP)
    )
    recorder = _recorder(preferences, store)

    suppressed = recorder.record(_notification(), event_id="evt-1")
    assert suppressed.suppressed is True

    preferences.save(NotificationPreferences(user_id=USER))  # user turns it back on
    replay = recorder.record(_notification(), event_id="evt-1")

    assert replay.recorded is True
    assert replay.duplicate is False
    assert replay.notification is not None


def test_suppression_does_not_report_a_duplicate(preferences, store):
    """Two different outcomes with two different causes; conflating them would make a muted
    user's logs read as if the bus were redelivering."""
    preferences.save(
        NotificationPreferences(user_id=USER).muting(CONFIRMED, PUSH).muting(CONFIRMED, IN_APP)
    )
    recorder = _recorder(preferences, store)

    result = recorder.record(_notification(), event_id="evt-1")

    assert (result.suppressed, result.duplicate) == (True, False)


def test_deduplication_still_applies_to_a_narrowed_notification(preferences, store):
    preferences.save(NotificationPreferences(user_id=USER).muting(CONFIRMED, PUSH))
    repository = InMemoryNotificationRepository(policy=TEST_POLICY)
    recorder = _recorder(preferences, store, repository)

    first = recorder.record(_notification(), event_id="evt-1")
    second = recorder.record(_notification(), event_id="evt-1")

    assert first.recorded is True
    assert second.duplicate is True
    assert len(repository.list_for_user(USER)) == 1


# -- failing open -----------------------------------------------------------------------


def test_an_unreadable_preference_store_delivers_unfiltered(store, caplog):
    """One unwanted notification is an annoyance the user can report. A silent, service-wide
    notification outage is not, so the recoverable failure is the one we choose."""
    recorder = _recorder(_ExplodingPreferences(), store)

    with caplog.at_level("WARNING"):
        result = recorder.record(_notification(), event_id="evt-1")

    assert result.recorded is True
    assert result.notification is not None
    assert result.notification.channels == (IN_APP, PUSH)
    assert any("preferences.unavailable" in record.message for record in caplog.records)


def test_a_recorder_without_a_preferences_port_delivers_unfiltered(store):
    """The port is optional so the NTF-102/103 wiring keeps working untouched."""
    recorder = NotificationRecorder(InMemoryNotificationRepository(policy=TEST_POLICY), store)

    result = recorder.record(_notification(), event_id="evt-1")

    assert result.recorded is True
    assert result.notification is not None
    assert result.notification.channels == (IN_APP, PUSH)
