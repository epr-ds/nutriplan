"""The loop that keeps consuming (NTF-201, AC3).

The worker owns exactly two things worth testing: when it sweeps for stranded messages, and
whether it survives a cycle that raises. Everything else it does is delegated to the
dispatcher, so these tests drive a stub dispatcher rather than a real bus -- the question
here is loop control flow, and a real consumer would only make the failure cases harder to
provoke.
"""

from __future__ import annotations

import signal
from collections.abc import Callable

import pytest

from app.core.config import Settings
from app.events.dispatcher import BatchResult
from app.events.worker import RECLAIM_EVERY_CYCLES, EventWorker, StopSignal


class StubDispatcher:
    """Records the calls the worker makes, and can be told to fail on cue."""

    def __init__(self, *, fail_on: set[int] | None = None) -> None:
        self.subscribed = 0
        self.polls: list[tuple[int, int]] = []
        self.reclaims: list[tuple[int, int]] = []
        self._fail_on = fail_on or set()

    def ensure_subscribed(self) -> None:
        self.subscribed += 1

    def poll_once(self, *, count: int, block_ms: int) -> BatchResult:
        self.polls.append((count, block_ms))
        if len(self.polls) in self._fail_on:
            raise ConnectionError("redis went away")
        return BatchResult(handled=1)

    def reclaim_once(self, *, min_idle_ms: int, count: int) -> BatchResult:
        self.reclaims.append((min_idle_ms, count))
        return BatchResult(dead_lettered=1)


class Sleeps:
    """A stand-in for ``time.sleep`` -- the backoff is asserted, never actually waited out."""

    def __init__(self) -> None:
        self.durations: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.durations.append(seconds)


def worker(
    dispatcher: StubDispatcher,
    *,
    batch_size: int = 10,
    block_ms: int = 2_000,
    reclaim_idle_ms: int = 60_000,
    reclaim_every: int = RECLAIM_EVERY_CYCLES,
    sleep: Callable[[float], None] | None = None,
) -> EventWorker:
    return EventWorker(
        dispatcher,  # type: ignore[arg-type]
        batch_size=batch_size,
        block_ms=block_ms,
        reclaim_idle_ms=reclaim_idle_ms,
        reclaim_every=reclaim_every,
        sleep=sleep,
    )


def stop_after(cycles: int) -> Callable[[], bool]:
    """A predicate that lets exactly ``cycles`` iterations run."""
    remaining = iter([False] * cycles + [True])
    return lambda: next(remaining, True)


class TestOneCycle:
    def test_it_polls_with_the_configured_batch_and_block(self) -> None:
        dispatcher = StubDispatcher()

        worker(dispatcher).run_once()

        assert dispatcher.polls == [(10, 2_000)]

    def test_the_first_cycle_sweeps_for_stranded_messages(self) -> None:
        """A worker starting up is often the replacement for one that just died."""
        dispatcher = StubDispatcher()

        worker(dispatcher).run_once()

        assert dispatcher.reclaims == [(60_000, 10)]

    def test_it_returns_the_combined_result_of_both_passes(self) -> None:
        assert worker(StubDispatcher()).run_once() == BatchResult(handled=1, dead_lettered=1)

    def test_the_sweep_is_periodic_not_per_cycle(self) -> None:
        """A reclaim finds nothing almost every time; running it each cycle is pure cost."""
        dispatcher = StubDispatcher()
        subject = worker(dispatcher, reclaim_every=3)

        for _ in range(7):
            subject.run_once()

        assert len(dispatcher.polls) == 7
        assert len(dispatcher.reclaims) == 3

    def test_the_default_sweep_interval_is_the_documented_one(self) -> None:
        dispatcher = StubDispatcher()
        subject = worker(dispatcher)

        for _ in range(RECLAIM_EVERY_CYCLES + 1):
            subject.run_once()

        assert len(dispatcher.reclaims) == 2

    def test_a_nonsensical_batch_size_is_clamped(self) -> None:
        """Polling for zero messages would be a silent, total outage."""
        dispatcher = StubDispatcher()

        worker(dispatcher, batch_size=0).run_once()

        assert dispatcher.polls == [(1, 2_000)]

    def test_a_negative_block_is_clamped(self) -> None:
        dispatcher = StubDispatcher()

        worker(dispatcher, block_ms=-1).run_once()

        assert dispatcher.polls == [(10, 0)]


class TestTheLoop:
    def test_it_subscribes_once_before_consuming(self) -> None:
        dispatcher = StubDispatcher()

        worker(dispatcher).run(stop_after(3))

        assert dispatcher.subscribed == 1

    def test_it_stops_when_the_predicate_says_so(self) -> None:
        dispatcher = StubDispatcher()

        worker(dispatcher).run(stop_after(3))

        assert len(dispatcher.polls) == 3

    def test_a_worker_told_to_stop_immediately_never_polls(self) -> None:
        """The predicate is checked before a cycle, not after -- no batch is abandoned."""
        dispatcher = StubDispatcher()

        worker(dispatcher).run(lambda: True)

        assert dispatcher.polls == []
        assert dispatcher.subscribed == 1

    def test_it_totals_what_every_cycle_settled(self) -> None:
        total = worker(StubDispatcher(), reclaim_every=100).run(stop_after(3))

        assert total == BatchResult(handled=3, dead_lettered=1)


class TestSurvivingABrokerOutage:
    def test_a_failed_cycle_does_not_end_the_loop(self) -> None:
        """Exiting would put the process in a crash loop against an outage it cannot fix."""
        dispatcher = StubDispatcher(fail_on={2})

        worker(dispatcher, sleep=Sleeps()).run(stop_after(4))

        assert len(dispatcher.polls) == 4

    def test_it_backs_off_before_trying_again(self) -> None:
        sleeps = Sleeps()
        dispatcher = StubDispatcher(fail_on={1, 2})

        worker(dispatcher, sleep=sleeps).run(stop_after(4))

        assert sleeps.durations == [5.0, 5.0]

    def test_a_healthy_cycle_never_sleeps(self) -> None:
        sleeps = Sleeps()

        worker(StubDispatcher(), sleep=sleeps).run(stop_after(3))

        assert sleeps.durations == []

    def test_the_failure_is_logged_with_a_traceback(self, caplog: pytest.LogCaptureFixture) -> None:
        """A swallowed exception with no trace is how an outage becomes unexplainable."""
        dispatcher = StubDispatcher(fail_on={1})

        with caplog.at_level("ERROR"):
            worker(dispatcher, sleep=Sleeps()).run(stop_after(2))

        assert "notification.event.cycle_failed" in caplog.text
        assert "ConnectionError" in caplog.text

    def test_a_failed_cycle_contributes_nothing_to_the_total(self) -> None:
        """Nothing was acked, so its messages are still pending for the next pass."""
        dispatcher = StubDispatcher(fail_on={1})

        total = worker(dispatcher, reclaim_every=100, sleep=Sleeps()).run(stop_after(2))

        # Two sweeps ran -- the cycle counter does not advance through a failure, so the
        # retry sweeps again -- but only the surviving cycle's result was counted.
        assert len(dispatcher.reclaims) == 2
        assert total == BatchResult(handled=1, dead_lettered=1)


class TestTheStopSignal:
    def test_it_starts_unset(self) -> None:
        assert StopSignal()() is False

    def test_a_signal_flips_it(self) -> None:
        stop = StopSignal()

        stop._handle(signal.SIGTERM, None)

        assert stop() is True

    def test_installing_registers_the_signals_an_orchestrator_sends(self) -> None:
        """SIGTERM is what Kubernetes sends first; SIGINT is Ctrl-C in a dev shell."""
        original = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
        try:
            stop = StopSignal().install()

            assert signal.getsignal(signal.SIGTERM) == stop._handle
            assert signal.getsignal(signal.SIGINT) == stop._handle
        finally:
            for sig, handler in original.items():
                signal.signal(sig, handler)


class TestBuildingFromSettings:
    def test_it_reads_the_batch_and_block_from_configuration(self) -> None:
        dispatcher = StubDispatcher()
        settings = Settings(event_batch_size=25, event_block_ms=500, event_reclaim_idle_ms=1_000)

        EventWorker.from_settings(settings, dispatcher=dispatcher).run_once()  # type: ignore[arg-type]

        assert dispatcher.polls == [(25, 500)]
        assert dispatcher.reclaims == [(1_000, 25)]

    def test_a_prewired_dispatcher_is_used_as_given(self) -> None:
        """NTF-202 builds a dispatcher with its handlers attached and hands it over."""
        dispatcher = StubDispatcher()

        EventWorker.from_settings(Settings(), dispatcher=dispatcher).run_once()  # type: ignore[arg-type]

        assert len(dispatcher.polls) == 1

    def test_it_builds_a_working_worker_with_no_arguments_at_all(self) -> None:
        """The path ``python -m app.events.worker`` takes -- it must not need wiring."""
        assert isinstance(EventWorker.from_settings(), EventWorker)
