"""The growing wait between retries of a failing delivery (NTF-204, AC1).

The schedule is pure arithmetic, so these tests are about the *properties* the rest of the
system relies on rather than about particular numbers: that the wait grows, that it is
bounded, that two replicas computing it independently agree, and that it never dips below
the idle floor that keeps a reclaim from stealing work another consumer is still doing.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from app.events.backoff import (
    DEFAULT_CAP_MS,
    DEFAULT_JITTER,
    DEFAULT_MULTIPLIER,
    RetrySchedule,
)

BASE = 60_000
"""The reclaim idle window the service actually runs with, in ms."""


def nominal() -> RetrySchedule:
    """A schedule with jitter off, so a delay is a single readable number."""
    return RetrySchedule(base_ms=BASE, jitter=0.0)


class TestTheWaitGrowsWithTheAttempt:
    def test_the_first_attempt_waits_the_base(self) -> None:
        """Attempt 1 has been delivered once, so its wait is the un-multiplied base."""
        assert nominal().delay_for(1) == BASE

    @pytest.mark.parametrize(
        ("attempt", "expected"),
        [(1, BASE), (2, BASE * 2), (3, BASE * 4), (4, BASE * 8)],
    )
    def test_each_further_attempt_doubles(self, attempt: int, expected: int) -> None:
        assert nominal().delay_for(attempt) == expected

    def test_a_nonsensical_attempt_is_treated_as_the_first(self) -> None:
        """A zero or negative delivery count is a broker quirk, not a reason to crash."""
        schedule = nominal()

        assert schedule.delay_for(0) == BASE
        assert schedule.delay_for(-3) == BASE

    def test_the_multiplier_is_configurable(self) -> None:
        schedule = RetrySchedule(base_ms=1_000, multiplier=3.0, jitter=0.0)

        assert schedule.delay_for(3) == 9_000


class TestTheWaitIsBounded:
    def test_it_never_exceeds_the_cap(self) -> None:
        """Otherwise the time-to-park grows without limit and nothing ever reaches the DLQ."""
        schedule = RetrySchedule(base_ms=BASE, cap_ms=300_000, jitter=0.0)

        assert schedule.delay_for(99) == 300_000

    def test_the_cap_is_reached_rather_than_approached(self) -> None:
        schedule = RetrySchedule(base_ms=1_000, cap_ms=4_000, jitter=0.0)

        assert [schedule.delay_for(n) for n in range(1, 6)] == [1_000, 2_000, 4_000, 4_000, 4_000]

    def test_a_cap_below_the_base_is_raised_to_it(self) -> None:
        """A misconfigured cap must not push a retry inside the idle floor."""
        schedule = RetrySchedule(base_ms=BASE, cap_ms=10, jitter=0.0)

        assert schedule.delay_for(1) == BASE


class TestDueness:
    def test_an_entry_idle_long_enough_is_due(self) -> None:
        assert nominal().is_due(attempt=1, idle_ms=BASE) is True

    def test_an_entry_idle_a_moment_short_is_not(self) -> None:
        assert nominal().is_due(attempt=1, idle_ms=BASE - 1) is False

    def test_a_later_attempt_needs_longer(self) -> None:
        """The same idle time that released attempt 1 holds attempt 3 back."""
        schedule = nominal()

        assert schedule.is_due(attempt=1, idle_ms=BASE) is True
        assert schedule.is_due(attempt=3, idle_ms=BASE) is False


class TestTheIdleFloor:
    def test_the_floor_is_what_a_prefilter_may_ask_the_broker_for(self) -> None:
        """Below the nominal base by exactly the jitter, so no due entry is filtered out."""
        schedule = RetrySchedule(base_ms=BASE, jitter=0.25)

        assert schedule.floor_ms == 45_000

    def test_no_entry_is_ever_due_before_the_floor(self) -> None:
        """The property the pre-filter depends on: asking for ``floor_ms`` misses nothing."""
        schedule = RetrySchedule(base_ms=BASE)
        floor = schedule.floor_ms

        for delivery_id in (f"1699999999999-{n}" for n in range(200)):
            assert schedule.delay_for(1, delivery_id=delivery_id) >= floor

    def test_with_no_jitter_the_floor_is_the_base(self) -> None:
        assert nominal().floor_ms == BASE


class TestJitter:
    def test_two_entries_get_different_offsets(self) -> None:
        """The point of the spread: a herd of retries does not arrive in one sweep."""
        schedule = RetrySchedule(base_ms=BASE)

        delays = {schedule.delay_for(1, delivery_id=f"1699999999999-{n}") for n in range(50)}

        assert len(delays) > 25

    def test_the_same_entry_always_gets_the_same_offset(self) -> None:
        schedule = RetrySchedule(base_ms=BASE)

        first = schedule.delay_for(2, delivery_id="1699999999999-7")
        again = schedule.delay_for(2, delivery_id="1699999999999-7")

        assert first == again

    def test_jitter_only_ever_moves_a_retry_earlier(self) -> None:
        """Spreading upward would let the cap be exceeded and unbound the time-to-park."""
        schedule = RetrySchedule(base_ms=BASE)
        ceiling = schedule.delay_for(1)

        for delivery_id in (f"1699999999999-{n}" for n in range(200)):
            assert schedule.delay_for(1, delivery_id=delivery_id) <= ceiling

    def test_an_absent_delivery_id_gives_the_nominal_schedule(self) -> None:
        """So a caller reasoning about the schedule itself is not reading a hashed number."""
        assert RetrySchedule(base_ms=BASE).delay_for(1, delivery_id="") == BASE

    def test_zero_jitter_removes_the_spread_entirely(self) -> None:
        schedule = RetrySchedule(base_ms=BASE, jitter=0.0)

        assert schedule.delay_for(1, delivery_id="1699999999999-7") == BASE


class TestEveryReplicaAgrees:
    def test_the_offset_survives_a_fresh_interpreter(self) -> None:
        """The reason for blake2b over ``hash``.

        Python randomises string hashing per process, so a schedule built on it would give
        two replicas -- or one pod either side of a restart -- different answers about
        whether the same entry is due. One would claim while the other deferred, and the
        spread would be decided by whoever swept first, which is no spread at all.

        Run in a subprocess rather than with a patched ``PYTHONHASHSEED``, because the seed
        is consumed at interpreter start and cannot be changed from inside one.
        """
        source = (
            "from app.events.backoff import RetrySchedule;"
            "print(RetrySchedule(base_ms=60000).delay_for(2, delivery_id='1699999999999-7'))"
        )
        here = RetrySchedule(base_ms=60_000).delay_for(2, delivery_id="1699999999999-7")

        elsewhere = subprocess.run(  # noqa: S603
            [sys.executable, "-c", source],
            capture_output=True,
            text=True,
            check=True,
        )

        assert int(elsewhere.stdout.strip()) == here


class TestMisconfigurationDegradesRatherThanCrashes:
    """These values arrive from the environment, and a worker that refuses to start has
    turned a typo into an outage of the consumer. Every bad value degrades to the flat
    NTF-201 behaviour instead."""

    def test_a_multiplier_below_one_is_raised_to_it(self) -> None:
        """A shrinking backoff would retry a failing handler faster the worse it got."""
        schedule = RetrySchedule(base_ms=BASE, multiplier=0.5, jitter=0.0)

        assert schedule.delay_for(4) == BASE

    def test_a_negative_base_becomes_no_wait(self) -> None:
        assert RetrySchedule(base_ms=-1).delay_for(1) == 0

    def test_jitter_outside_zero_to_one_is_clamped(self) -> None:
        assert RetrySchedule(base_ms=BASE, jitter=9.0).jitter == 1.0
        assert RetrySchedule(base_ms=BASE, jitter=-9.0).jitter == 0.0

    def test_the_schedule_is_immutable(self) -> None:
        """Shared by the worker and both consumer adapters -- one mutation would desync them."""
        schedule = RetrySchedule(base_ms=BASE)

        with pytest.raises((AttributeError, TypeError)):
            schedule.base_ms = 1  # type: ignore[misc]


class TestTheDefaults:
    def test_they_are_the_documented_ones(self) -> None:
        schedule = RetrySchedule(base_ms=BASE)

        assert (schedule.multiplier, schedule.cap_ms, schedule.jitter) == (
            DEFAULT_MULTIPLIER,
            DEFAULT_CAP_MS,
            DEFAULT_JITTER,
        )

    def test_the_budget_is_exhausted_well_inside_the_cap(self) -> None:
        """Five attempts at a 60s base must not take so long that the news is stale.

        The whole point of parking a poison message is that an operator finds it while the
        incident is still on; a schedule that took half a day to give up would be indistinguishable
        from one that never did.
        """
        schedule = RetrySchedule(base_ms=BASE, jitter=0.0)

        total_ms = sum(schedule.delay_for(attempt) for attempt in range(1, 6))

        assert total_ms < 45 * 60 * 1_000
