"""The nightly window in which a user's phone must not buzz (NTF-104, AC2).

A quiet-hours window is a pair of **local wall-clock times** plus the IANA zone they are
read in -- not an instant and not an offset. "Don't wake me between 22:00 and 07:00" is a
statement about the clock on the wall, and it must keep meaning that after the user flies to
another country or after a daylight-saving transition moves their offset. Storing an offset
(``-06:00``) instead of a zone name (``America/Mexico_City``) would silently shift the window
by an hour twice a year, which is exactly the kind of bug nobody reports and everybody
notices.

Two details carry most of the weight here.

**The window may wrap midnight, and the useful ones do.** ``22:00 -> 07:00`` is the ordinary
case, not an edge case, and the obvious ``start <= t <= end`` test returns ``False`` for every
minute of it. The comparison is therefore split on :attr:`wraps_midnight`, and both branches
are tested directly.

**Daylight saving is a non-issue only because of the direction of conversion.** This module
converts a known *instant* into local time (``instant.astimezone(zone)``), never a local time
into an instant. That direction is always well-defined: every instant has exactly one local
representation. The opposite direction is not -- during a spring-forward gap a wall-clock time
may not exist at all, and during a fall-back fold it happens twice -- so a design that built
"today's 22:00 in the user's zone" and compared instants would have to answer questions with
no correct answer. Comparing wall clock to wall clock sidesteps that entirely: on the night
the clocks go back, 01:30 simply falls inside the window both times it occurs, which is what
a sleeping user means.

The interval is **half-open**: ``start`` is inside the window and ``end`` is the first minute
outside it, so a 22:00-07:00 window is quiet at 22:00 sharp and audible at 07:00 sharp. That
convention is the reason ``start == end`` is rejected rather than interpreted -- read one way
it is an empty window, read the other it is a whole silent day, and both readings are
defensible enough that guessing would be wrong for half the users who managed to set it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.errors import InvalidPreferences

DEFAULT_TIME_ZONE = "America/Mexico_City"
"""Where most NutriPlan users are; matches the app's ``mx.`` bundle id."""


def resolve_zone(name: str) -> ZoneInfo:
    """Return the IANA zone called ``name``, or raise :class:`InvalidPreferences`.

    ``ZoneInfo`` raises :class:`ZoneInfoNotFoundError` for an unknown zone and
    :class:`ValueError` for a malformed key (it refuses absolute and ``..``-relative paths,
    since the name reaches the filesystem). Both are user input errors here, so both become
    one domain error the API renders as ``422``.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidPreferences(f"unknown time zone: {name!r}") from exc


@dataclass(frozen=True, slots=True)
class QuietHours:
    """A recurring daily window, in the user's own local time, during which push is withheld."""

    start: time
    end: time
    time_zone: str = DEFAULT_TIME_ZONE

    def __post_init__(self) -> None:
        for name, value in (("start", self.start), ("end", self.end)):
            if not isinstance(value, time):
                raise InvalidPreferences(f"{name} must be a time, got {type(value).__name__}")
            if value.tzinfo is not None:
                # An offset here would contradict ``time_zone`` and there is no sensible way
                # to reconcile the two, so the ambiguity is refused at the door.
                raise InvalidPreferences(
                    f"{name} must be a local wall-clock time without an offset"
                )
            if value.second or value.microsecond:
                raise InvalidPreferences(f"{name} must be given to the minute, got {value}")

        if self.start == self.end:
            raise InvalidPreferences(
                "start and end must differ: an empty window and an all-day window are both "
                "plausible readings of start == end, so neither is assumed"
            )

        resolve_zone(self.time_zone)

    @property
    def zone(self) -> ZoneInfo:
        """The resolved IANA zone (``zoneinfo`` caches these, so this is cheap to re-read)."""
        return resolve_zone(self.time_zone)

    @property
    def wraps_midnight(self) -> bool:
        """True for an overnight window such as ``22:00 -> 07:00``."""
        return self.end < self.start

    def local_time(self, instant: datetime) -> time:
        """Express ``instant`` as a wall-clock time in this window's zone.

        Requires an aware datetime. A naive one would be silently read as the *server's*
        local time, which in a container is UTC -- so a user in Mexico City would be judged
        against a clock six hours ahead of their own, and quiet hours would appear to start
        in the afternoon.
        """
        if instant.tzinfo is None or instant.tzinfo.utcoffset(instant) is None:
            raise InvalidPreferences("instant must be timezone-aware to be read as local time")
        return instant.astimezone(self.zone).time()

    def covers(self, instant: datetime) -> bool:
        """True when ``instant`` falls inside the window, in the user's local time.

        Half-open: ``start`` is inside, ``end`` is not.
        """
        moment = self.local_time(instant)
        if self.wraps_midnight:
            return moment >= self.start or moment < self.end
        return self.start <= moment < self.end
