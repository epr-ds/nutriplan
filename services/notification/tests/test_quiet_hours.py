"""NTF-104: the nightly window in which a user's phone must not buzz.

Pure domain tests -- no store, no clock, no network. The three things worth pinning here are
the ones a plausible-looking reimplementation gets wrong: midnight wrapping (the *common*
case, which a naive ``start <= t <= end`` misses entirely), the half-open boundary, and the
fact that daylight saving does not perturb the answer because the comparison happens in wall
clock rather than in instants.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.domain.errors import InvalidPreferences
from app.domain.quiet_hours import DEFAULT_TIME_ZONE, QuietHours, resolve_zone

MEXICO_CITY = "America/Mexico_City"
NEW_YORK = "America/New_York"


def _at(zone: str, year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """A real instant, expressed by its local wall-clock reading in ``zone``."""
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(zone))


# -- construction -----------------------------------------------------------------------


def test_the_default_zone_resolves():
    """A default that does not resolve would fail at the first write, not at import."""
    assert resolve_zone(DEFAULT_TIME_ZONE).key == DEFAULT_TIME_ZONE


def test_an_unknown_zone_is_a_domain_error():
    with pytest.raises(InvalidPreferences, match="unknown time zone"):
        QuietHours(start=time(22, 0), end=time(7, 0), time_zone="Mars/Olympus_Mons")


def test_a_path_shaped_zone_name_is_refused():
    """The name reaches the filesystem, so traversal-shaped keys must not be tried."""
    with pytest.raises(InvalidPreferences, match="unknown time zone"):
        QuietHours(start=time(22, 0), end=time(7, 0), time_zone="../../etc/passwd")


def test_start_equal_to_end_is_refused_rather_than_interpreted():
    """Empty window and all-day window are both defensible readings, so neither is assumed."""
    with pytest.raises(InvalidPreferences, match="must differ"):
        QuietHours(start=time(22, 0), end=time(22, 0))


def test_a_time_carrying_an_offset_is_refused():
    """An offset on the time would contradict ``time_zone`` with no way to reconcile them."""
    with pytest.raises(InvalidPreferences, match="without an offset"):
        QuietHours(start=time(22, 0, tzinfo=timezone(timedelta(hours=-6))), end=time(7, 0))


def test_sub_minute_precision_is_refused():
    """Users set quiet hours to the minute; storing 22:00:30 would only ever be a bug."""
    with pytest.raises(InvalidPreferences, match="to the minute"):
        QuietHours(start=time(22, 0, 30), end=time(7, 0))


def test_a_window_is_immutable():
    window = QuietHours(start=time(22, 0), end=time(7, 0))
    with pytest.raises((AttributeError, TypeError)):
        window.start = time(23, 0)  # type: ignore[misc]


# -- wrapping ---------------------------------------------------------------------------


def test_an_overnight_window_is_recognised_as_wrapping():
    assert QuietHours(start=time(22, 0), end=time(7, 0)).wraps_midnight is True


def test_a_same_day_window_does_not_wrap():
    assert QuietHours(start=time(13, 0), end=time(15, 0)).wraps_midnight is False


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (21, 59, False),  # just before it starts
        (22, 0, True),  # start is inclusive
        (23, 30, True),  # before midnight
        (0, 0, True),  # midnight itself, the case a naive comparison drops
        (3, 15, True),  # after midnight
        (6, 59, True),  # last quiet minute
        (7, 0, False),  # end is exclusive
        (12, 0, False),  # broad daylight
    ],
)
def test_an_overnight_window_covers_both_sides_of_midnight(hour, minute, expected):
    window = QuietHours(start=time(22, 0), end=time(7, 0), time_zone=MEXICO_CITY)
    assert window.covers(_at(MEXICO_CITY, 2026, 3, 10, hour, minute)) is expected


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (12, 59, False),
        (13, 0, True),
        (14, 30, True),
        (14, 59, True),
        (15, 0, False),
        (23, 0, False),
    ],
)
def test_a_same_day_window_is_half_open(hour, minute, expected):
    window = QuietHours(start=time(13, 0), end=time(15, 0), time_zone=MEXICO_CITY)
    assert window.covers(_at(MEXICO_CITY, 2026, 3, 10, hour, minute)) is expected


# -- zones ------------------------------------------------------------------------------


def test_the_window_is_read_in_the_users_zone_not_the_servers():
    """22:00 in Mexico City is 04:00 UTC the next day; a UTC reading would call it daytime."""
    window = QuietHours(start=time(22, 0), end=time(7, 0), time_zone=MEXICO_CITY)
    instant = datetime(2026, 3, 11, 4, 30, tzinfo=UTC)

    assert instant.astimezone(ZoneInfo(MEXICO_CITY)).hour == 22
    assert window.covers(instant) is True


def test_two_users_in_different_zones_disagree_about_the_same_instant():
    """The same wall-clock window, the same instant, two correct answers."""
    instant = datetime(2026, 3, 11, 12, 30, tzinfo=UTC)
    mexico = QuietHours(start=time(22, 0), end=time(7, 0), time_zone=MEXICO_CITY)
    new_york = QuietHours(start=time(22, 0), end=time(7, 0), time_zone=NEW_YORK)

    assert mexico.covers(instant) is True  # 06:30, still quiet
    assert new_york.covers(instant) is False  # 08:30, awake for hours


def test_a_naive_instant_is_refused():
    """A naive datetime would be read as the container's clock (UTC), not the user's."""
    window = QuietHours(start=time(22, 0), end=time(7, 0))
    with pytest.raises(InvalidPreferences, match="timezone-aware"):
        window.covers(datetime(2026, 3, 10, 23, 0))  # noqa: DTZ001


def test_local_time_projects_an_instant_onto_the_users_clock():
    window = QuietHours(start=time(22, 0), end=time(7, 0), time_zone=MEXICO_CITY)
    assert window.local_time(datetime(2026, 3, 11, 4, 30, tzinfo=UTC)) == time(22, 30)


# -- daylight saving --------------------------------------------------------------------
#
# These are the tests the whole "wall clock, never instants" decision exists for. New York
# springs forward on 2026-03-08 (02:00 -> 03:00) and falls back on 2026-11-01 (02:00 -> 01:00).


def test_the_window_still_means_ten_at_night_after_a_spring_forward():
    """The offset moved by an hour; the window must not move with it."""
    window = QuietHours(start=time(22, 0), end=time(7, 0), time_zone=NEW_YORK)

    before = datetime(2026, 3, 7, 22, 30, tzinfo=ZoneInfo(NEW_YORK))  # EST, -05:00
    after = datetime(2026, 3, 9, 22, 30, tzinfo=ZoneInfo(NEW_YORK))  # EDT, -04:00

    assert before.utcoffset() != after.utcoffset()
    assert window.covers(before) is True
    assert window.covers(after) is True


def test_the_hour_that_does_not_exist_needs_no_answer():
    """02:30 never happens on a spring-forward night; nothing here has to invent one.

    A design that materialised "today's 22:00 as an instant" would have to decide what that
    means during the gap. Converting the other way -- instant to wall clock -- is total, so
    the question never arises: whatever ``2026-03-08 02:30`` normalises to, it is judged by
    the clock the user would have been looking at.
    """
    window = QuietHours(start=time(22, 0), end=time(7, 0), time_zone=NEW_YORK)
    gap = datetime(2026, 3, 8, 2, 30, tzinfo=ZoneInfo(NEW_YORK))

    assert window.covers(gap) is window.covers(gap)  # total and deterministic
    assert isinstance(window.local_time(gap), time)


def test_both_occurrences_of_a_repeated_hour_are_quiet():
    """On a fall-back night 01:30 happens twice, and a sleeping user means both."""
    window = QuietHours(start=time(22, 0), end=time(7, 0), time_zone=NEW_YORK)

    first = datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo(NEW_YORK), fold=0)
    second = datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo(NEW_YORK), fold=1)

    assert first.utcoffset() != second.utcoffset()  # genuinely two different instants
    assert window.covers(first) is True
    assert window.covers(second) is True
