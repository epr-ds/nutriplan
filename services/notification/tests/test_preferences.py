"""NTF-104: what a user has chosen not to be told about.

Pure domain and application tests -- no store, no HTTP. The load-bearing claim being pinned
here is the storage shape: preferences are a **sparse deny-list of mutes**, so absent means
enabled, so a notification type added next release is on for every existing user without a
migration. Almost every test below is an instance of that one idea, plus the deliberate
asymmetry that quiet hours gate push and leave the in-app feed alone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.application.preferences import (
    NotificationPreferenceService,
    PreferenceMatrix,
    TypePreference,
    _collapse,
)
from app.domain.enums import NotificationChannel, NotificationType
from app.domain.errors import InvalidPreferences
from app.domain.preferences import NotificationPreferences
from app.domain.quiet_hours import QuietHours

USER = uuid.uuid4()
MEXICO_CITY = "America/Mexico_City"

NIGHT = QuietHours(start=time(22, 0), end=time(7, 0), time_zone=MEXICO_CITY)
LATE = datetime(2026, 3, 11, 5, 30, tzinfo=UTC)  # 23:30 in Mexico City
NOON = datetime(2026, 3, 11, 18, 30, tzinfo=UTC)  # 12:30 in Mexico City

IN_APP = NotificationChannel.IN_APP
PUSH = NotificationChannel.PUSH
CONFIRMED = NotificationType.ORDER_CONFIRMED
DELIVERED = NotificationType.ORDER_DELIVERED


# -- defaults ---------------------------------------------------------------------------


def test_a_user_who_never_opened_the_screen_has_everything_enabled():
    preferences = NotificationPreferences.defaults(USER)

    assert preferences.muted == frozenset()
    assert preferences.quiet_hours is None
    for notification_type in NotificationType:
        for channel in NotificationChannel:
            assert preferences.allows(notification_type, channel) is True


def test_a_notification_type_nobody_has_heard_of_is_enabled():
    """The whole reason the store holds mutes and not a matrix.

    A stored matrix written before a type existed cannot mention it; reading that absence as
    *disabled* would mute a brand-new notification for every existing user, with no error and
    nothing in the logs. Here the absence is what enables it.
    """
    preferences = NotificationPreferences(user_id=USER, muted={(CONFIRMED, PUSH)})

    unmentioned = NotificationType.MEAL_REMINDER
    assert preferences.is_muted(unmentioned, PUSH) is False
    assert preferences.allows(unmentioned, PUSH) is True


def test_updated_at_must_be_timezone_aware():
    """A naive timestamp would be read as the container's clock and compared against UTC."""
    with pytest.raises(InvalidPreferences, match="timezone-aware"):
        NotificationPreferences(user_id=USER, updated_at=datetime(2026, 3, 11, 5, 30))  # noqa: DTZ001


def test_updated_at_is_normalised_to_utc():
    local = datetime(2026, 3, 11, 5, 30, tzinfo=ZoneInfo(MEXICO_CITY))
    preferences = NotificationPreferences(user_id=USER, updated_at=local)

    assert preferences.updated_at.tzinfo is UTC
    assert preferences.updated_at == local


def test_a_decoded_mute_compares_equal_to_a_built_one():
    """Mutes arrive from JSON as plain strings; normalising them is what makes reads work."""
    from_wire = NotificationPreferences(user_id=USER, muted={("order_confirmed", "push")})
    built = NotificationPreferences(user_id=USER, muted={(CONFIRMED, PUSH)})

    assert from_wire.muted == built.muted
    assert from_wire.is_muted(CONFIRMED, PUSH) is True


def test_an_unknown_type_or_channel_is_refused():
    with pytest.raises(InvalidPreferences, match="unknown notification type or channel"):
        NotificationPreferences(user_id=USER, muted={("order_teleported", "push")})


def test_a_malformed_mute_is_refused():
    with pytest.raises(InvalidPreferences, match="must be a \\(type, channel\\) pair"):
        NotificationPreferences(user_id=USER, muted={("order_confirmed",)})


# -- opting out -------------------------------------------------------------------------


def test_a_mute_switches_off_exactly_one_pair():
    preferences = NotificationPreferences.defaults(USER).muting(CONFIRMED, PUSH)

    assert preferences.allows(CONFIRMED, PUSH) is False
    assert preferences.allows(CONFIRMED, IN_APP) is True  # other channel untouched
    assert preferences.allows(DELIVERED, PUSH) is True  # other type untouched


def test_muting_and_unmuting_round_trip():
    muted = NotificationPreferences.defaults(USER).muting(CONFIRMED, PUSH)
    restored = muted.unmuting(CONFIRMED, PUSH)

    assert restored.muted == frozenset()


def test_unmuting_something_that_was_never_muted_is_a_no_op():
    preferences = NotificationPreferences.defaults(USER).unmuting(CONFIRMED, PUSH)
    assert preferences.muted == frozenset()


def test_muting_returns_a_copy_and_leaves_the_original_alone():
    original = NotificationPreferences.defaults(USER)
    muted = original.muting(CONFIRMED, PUSH)

    assert original.muted == frozenset()
    assert muted is not original


def test_permitted_channels_filters_and_preserves_order():
    preferences = NotificationPreferences.defaults(USER).muting(CONFIRMED, PUSH)

    assert preferences.permitted_channels(CONFIRMED, (IN_APP, PUSH)) == (IN_APP,)
    assert preferences.permitted_channels(DELIVERED, (PUSH, IN_APP)) == (PUSH, IN_APP)


def test_muting_every_channel_leaves_nothing_permitted():
    preferences = (
        NotificationPreferences.defaults(USER).muting(CONFIRMED, PUSH).muting(CONFIRMED, IN_APP)
    )

    assert preferences.permitted_channels(CONFIRMED, (IN_APP, PUSH)) == ()


# -- quiet hours ------------------------------------------------------------------------


def test_quiet_hours_withhold_push_only():
    """The in-app feed is pull-based and silent, so there is nothing to spare the user by
    withholding an entry -- it would only arrive out of order in the morning, or not at all."""
    preferences = NotificationPreferences(user_id=USER, quiet_hours=NIGHT)

    assert preferences.allows(CONFIRMED, PUSH, at=LATE) is False
    assert preferences.allows(CONFIRMED, IN_APP, at=LATE) is True
    assert preferences.permitted_channels(CONFIRMED, (IN_APP, PUSH), at=LATE) == (IN_APP,)


def test_outside_quiet_hours_push_goes_out():
    preferences = NotificationPreferences(user_id=USER, quiet_hours=NIGHT)

    assert preferences.allows(CONFIRMED, PUSH, at=NOON) is True
    assert preferences.permitted_channels(CONFIRMED, (IN_APP, PUSH), at=NOON) == (IN_APP, PUSH)


def test_no_quiet_hours_means_never_quiet():
    preferences = NotificationPreferences.defaults(USER)
    assert preferences.in_quiet_hours(LATE) is False


def test_with_quiet_hours_sets_replaces_and_clears():
    preferences = NotificationPreferences.defaults(USER)

    assert preferences.with_quiet_hours(NIGHT).quiet_hours == NIGHT

    siesta = QuietHours(start=time(14, 0), end=time(16, 0), time_zone=MEXICO_CITY)
    assert preferences.with_quiet_hours(NIGHT).with_quiet_hours(siesta).quiet_hours == siesta
    assert preferences.with_quiet_hours(NIGHT).with_quiet_hours(None).quiet_hours is None


def test_channels_for_ignores_the_clock():
    """A settings screen renders what the user switched on. Folding a time-dependent
    suppression in would make the toggles appear to flick themselves off every night."""
    preferences = NotificationPreferences(user_id=USER, quiet_hours=NIGHT).muting(CONFIRMED, IN_APP)

    assert preferences.channels_for(CONFIRMED) == frozenset({PUSH})
    assert preferences.channels_for(DELIVERED) == frozenset({IN_APP, PUSH})


# -- the materialized matrix ------------------------------------------------------------


def test_the_matrix_has_a_row_for_every_type_in_declaration_order():
    matrix = PreferenceMatrix.from_preferences(NotificationPreferences.defaults(USER))

    assert tuple(row.type for row in matrix.types) == tuple(NotificationType)
    assert all(row.in_app and row.push for row in matrix.types)


def test_the_matrix_reflects_stored_mutes():
    preferences = NotificationPreferences.defaults(USER).muting(CONFIRMED, PUSH)
    matrix = PreferenceMatrix.from_preferences(preferences)

    row = next(r for r in matrix.types if r.type is CONFIRMED)
    assert (row.in_app, row.push) == (True, False)
    assert all(r.in_app and r.push for r in matrix.types if r.type is not CONFIRMED)


def test_the_matrix_carries_quiet_hours_and_the_timestamp():
    stored = NotificationPreferences(user_id=USER, quiet_hours=NIGHT)
    matrix = PreferenceMatrix.from_preferences(stored)

    assert matrix.quiet_hours == NIGHT
    assert matrix.updated_at == stored.updated_at
    assert matrix.user_id == USER


def test_a_row_collapses_back_to_the_mutes_it_switches_off():
    assert TypePreference(type=CONFIRMED).mutes() == ()
    assert TypePreference(type=CONFIRMED, push=False).mutes() == ((CONFIRMED, PUSH),)
    assert set(TypePreference(type=CONFIRMED, in_app=False, push=False).mutes()) == {
        (CONFIRMED, IN_APP),
        (CONFIRMED, PUSH),
    }


def test_collapsing_a_full_matrix_of_defaults_stores_nothing():
    rows = [TypePreference(type=t) for t in NotificationType]
    assert _collapse(rows) == frozenset()


def test_a_duplicate_row_is_refused_rather_than_resolved_last_wins():
    """Two rows for one type are two different answers to the same question. Honouring one
    would leave the user looking at a screen that disagrees with what was saved."""
    rows = [
        TypePreference(type=CONFIRMED, push=False),
        TypePreference(type=CONFIRMED, push=True),
    ]
    with pytest.raises(InvalidPreferences, match="duplicate preference row"):
        _collapse(rows)


def test_expanding_and_collapsing_round_trips():
    stored = (
        NotificationPreferences.defaults(USER)
        .muting(CONFIRMED, PUSH)
        .muting(DELIVERED, IN_APP)
        .with_quiet_hours(NIGHT)
    )
    matrix = PreferenceMatrix.from_preferences(stored)

    assert _collapse(matrix.types) == stored.muted


# -- the service ------------------------------------------------------------------------


class _StubRepository:
    """Just enough of the port to drive the service without a store."""

    def __init__(self, stored: NotificationPreferences | None = None) -> None:
        self.stored = stored
        self.saved: list[NotificationPreferences] = []

    def get(self, user_id: uuid.UUID) -> NotificationPreferences | None:
        return self.stored if self.stored and self.stored.user_id == user_id else None

    def save(self, preferences: NotificationPreferences) -> NotificationPreferences:
        self.saved.append(preferences)
        self.stored = preferences
        return preferences


def test_get_returns_defaults_for_a_user_who_has_never_saved():
    """Not a 404: they *do* have preferences -- the defaults -- and the screen must render."""
    service = NotificationPreferenceService(_StubRepository())

    matrix = service.get(USER)

    assert matrix.user_id == USER
    assert len(matrix.types) == len(NotificationType)
    assert all(row.in_app and row.push for row in matrix.types)


def test_get_returns_what_was_stored():
    stored = NotificationPreferences.defaults(USER).muting(CONFIRMED, PUSH)
    service = NotificationPreferenceService(_StubRepository(stored))

    row = next(r for r in service.get(USER).types if r.type is CONFIRMED)
    assert row.push is False


def test_replace_stores_only_the_exceptions():
    repository = _StubRepository()
    service = NotificationPreferenceService(repository)

    service.replace(
        USER,
        types=[TypePreference(type=t, push=t is not CONFIRMED) for t in NotificationType],
        quiet_hours=None,
    )

    assert repository.saved[-1].muted == frozenset({(CONFIRMED, PUSH)})


def test_replace_is_a_full_replacement_so_an_omitted_type_returns_to_default():
    """A client running last month's build omits a row it has never heard of; replacement
    says exactly what the settings are now, which is also what that client is displaying."""
    repository = _StubRepository(NotificationPreferences.defaults(USER).muting(CONFIRMED, PUSH))
    service = NotificationPreferenceService(repository)

    matrix = service.replace(
        USER, types=[TypePreference(type=DELIVERED, push=False)], quiet_hours=None
    )

    assert repository.saved[-1].muted == frozenset({(DELIVERED, PUSH)})
    assert next(r for r in matrix.types if r.type is CONFIRMED).push is True


def test_replace_sets_and_clears_quiet_hours():
    repository = _StubRepository()
    service = NotificationPreferenceService(repository)

    assert service.replace(USER, types=[], quiet_hours=NIGHT).quiet_hours == NIGHT
    assert service.replace(USER, types=[], quiet_hours=None).quiet_hours is None


def test_replace_stamps_a_fresh_updated_at():
    repository = _StubRepository()
    service = NotificationPreferenceService(repository)

    before = datetime.now(UTC) - timedelta(seconds=1)
    matrix = service.replace(USER, types=[], quiet_hours=None)

    assert matrix.updated_at >= before


def test_replace_refuses_a_duplicate_row_before_writing_anything():
    repository = _StubRepository()
    service = NotificationPreferenceService(repository)

    with pytest.raises(InvalidPreferences):
        service.replace(
            USER,
            types=[TypePreference(type=CONFIRMED), TypePreference(type=CONFIRMED, push=False)],
            quiet_hours=None,
        )

    assert repository.saved == []
