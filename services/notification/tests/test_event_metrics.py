"""Counting what happened to each delivery (NTF-204, AC3).

NTF-706 owns the exporter, the dashboards and the alerts; this module only has to produce
honest numbers for it to read. So these tests are about the arithmetic and the shape of the
snapshot, not about anything being scraped.
"""

from __future__ import annotations

import threading

import pytest

from app.events.metrics import UNTYPED, EventMetrics, Outcome


class TestCounting:
    def test_every_outcome_starts_at_zero(self) -> None:
        """An absent series and a series at zero look the same on a graph and are not.

        Pre-seeding every outcome means a rate of zero is visibly zero from the first
        scrape, rather than a gap someone has to interpret.
        """
        metrics = EventMetrics()

        assert all(metrics.total(outcome) == 0 for outcome in Outcome)

    def test_an_increment_is_counted(self) -> None:
        metrics = EventMetrics()

        metrics.increment(Outcome.HANDLED)

        assert metrics.total(Outcome.HANDLED) == 1

    def test_increments_accumulate(self) -> None:
        metrics = EventMetrics()

        for _ in range(3):
            metrics.increment(Outcome.RETRIED)

        assert metrics.total(Outcome.RETRIED) == 3

    def test_a_batch_can_be_counted_at_once(self) -> None:
        """``reclaim_once`` reports its deferred entries as one number, not one at a time."""
        metrics = EventMetrics()

        metrics.increment(Outcome.DEFERRED, count=7)

        assert metrics.total(Outcome.DEFERRED) == 7

    def test_the_outcomes_are_independent(self) -> None:
        metrics = EventMetrics()

        metrics.increment(Outcome.HANDLED)
        metrics.increment(Outcome.DEAD_LETTERED)

        assert metrics.total(Outcome.HANDLED) == 1
        assert metrics.total(Outcome.DEAD_LETTERED) == 1
        assert metrics.total(Outcome.DROPPED) == 0

    @pytest.mark.parametrize("count", [0, -1, -100])
    def test_a_non_positive_count_changes_nothing(self, count: int) -> None:
        """An empty batch reports zero deferred, and that must not decrement the series."""
        metrics = EventMetrics()
        metrics.increment(Outcome.HANDLED, count=3)

        metrics.increment(Outcome.HANDLED, count=count)

        assert metrics.total(Outcome.HANDLED) == 3


class TestTheBreakdownByEventType:
    def test_a_type_gets_its_own_count(self) -> None:
        """Which event is failing is the first question an alert on a rate raises."""
        metrics = EventMetrics()

        metrics.increment(Outcome.DEAD_LETTERED, event_type="order.confirmed")

        assert metrics.by_type(Outcome.DEAD_LETTERED) == {"order.confirmed": 1}

    def test_types_are_counted_separately(self) -> None:
        metrics = EventMetrics()

        metrics.increment(Outcome.HANDLED, event_type="order.confirmed")
        metrics.increment(Outcome.HANDLED, event_type="order.status_changed", count=2)

        assert metrics.by_type(Outcome.HANDLED) == {
            "order.confirmed": 1,
            "order.status_changed": 2,
        }

    def test_the_breakdown_sums_to_the_total(self) -> None:
        metrics = EventMetrics()
        metrics.increment(Outcome.HANDLED, event_type="order.confirmed")
        metrics.increment(Outcome.HANDLED, event_type="order.status_changed", count=2)

        assert sum(metrics.by_type(Outcome.HANDLED).values()) == metrics.total(Outcome.HANDLED)

    def test_an_unparseable_event_gets_a_label_rather_than_being_dropped(self) -> None:
        """A payload too broken to name is the most interesting one on the graph.

        Leaving the label out would let those vanish from the breakdown while still counting
        in the total, so the two would disagree in exactly the situation someone is looking
        at them to explain.
        """
        metrics = EventMetrics()

        metrics.increment(Outcome.DEAD_LETTERED)

        assert metrics.by_type(Outcome.DEAD_LETTERED) == {UNTYPED: 1}

    def test_an_empty_type_is_labelled_the_same_way(self) -> None:
        metrics = EventMetrics()

        metrics.increment(Outcome.DEAD_LETTERED, event_type="")

        assert metrics.by_type(Outcome.DEAD_LETTERED) == {UNTYPED: 1}

    def test_the_breakdowns_are_per_outcome(self) -> None:
        metrics = EventMetrics()

        metrics.increment(Outcome.HANDLED, event_type="order.confirmed")
        metrics.increment(Outcome.RETRIED, event_type="order.confirmed")

        assert metrics.by_type(Outcome.HANDLED) == {"order.confirmed": 1}
        assert metrics.by_type(Outcome.RETRIED) == {"order.confirmed": 1}

    def test_the_returned_breakdown_is_a_copy(self) -> None:
        """A caller mutating a view of the counters would corrupt them silently."""
        metrics = EventMetrics()
        metrics.increment(Outcome.HANDLED, event_type="order.confirmed")

        snapshot = dict(metrics.by_type(Outcome.HANDLED))
        snapshot["order.confirmed"] = 999

        assert metrics.by_type(Outcome.HANDLED) == {"order.confirmed": 1}


class TestTheSnapshot:
    def test_it_always_carries_every_total(self) -> None:
        snapshot = EventMetrics().snapshot()

        assert set(snapshot["totals"]) == {outcome.value for outcome in Outcome}

    def test_totals_are_reported_under_their_outcome_names(self) -> None:
        metrics = EventMetrics()
        metrics.increment(Outcome.DEAD_LETTERED, count=2)

        assert metrics.snapshot()["totals"]["dead_lettered"] == 2

    def test_a_used_outcome_gets_its_breakdown(self) -> None:
        metrics = EventMetrics()
        metrics.increment(Outcome.HANDLED, event_type="order.confirmed")

        assert metrics.snapshot()["handled"] == {"order.confirmed": 1}

    def test_an_unused_outcome_has_no_breakdown_section(self) -> None:
        """Totals are the series; an empty breakdown is noise in every scrape forever."""
        metrics = EventMetrics()
        metrics.increment(Outcome.HANDLED, event_type="order.confirmed")

        assert "retried" not in metrics.snapshot()

    def test_it_is_json_native(self) -> None:
        """The DLQ CLI's ``--json`` mode pipes this straight into ``jq``."""
        import json

        metrics = EventMetrics()
        metrics.increment(Outcome.REPLAYED, event_type="order.confirmed")

        assert json.loads(json.dumps(metrics.snapshot()))["replayed"] == {"order.confirmed": 1}

    def test_it_is_a_point_in_time_copy(self) -> None:
        """One consistent read, so a snapshot taken mid-batch cannot show a delivery counted
        as neither handled nor retried -- arithmetic that sends someone hunting a bug in the
        consumer instead of in the dashboard."""
        metrics = EventMetrics()
        metrics.increment(Outcome.HANDLED)

        snapshot = metrics.snapshot()
        metrics.increment(Outcome.HANDLED)

        assert snapshot["totals"]["handled"] == 1


class TestConcurrency:
    def test_no_increment_is_lost_under_parallel_writers(self) -> None:
        """The worker settles on its own thread while a replay runs on another; a lost
        increment surfaces only much later, as a graph that does not add up."""
        metrics = EventMetrics()

        def bump() -> None:
            for _ in range(500):
                metrics.increment(Outcome.HANDLED, event_type="order.confirmed")

        threads = [threading.Thread(target=bump) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert metrics.total(Outcome.HANDLED) == 2_000
        assert metrics.by_type(Outcome.HANDLED) == {"order.confirmed": 2_000}


class TestWhatIsDeliberatelyNotCounted:
    def test_there_is_no_queue_depth_series(self) -> None:
        """Depth is read off the queue, never accumulated here.

        A parks-minus-removes counter drifts the moment an entry expires by TTL or a second
        replica removes one, and it drifts *upward* -- so the alert that matters would fire
        on a queue that is actually empty.
        """
        assert not any("depth" in outcome.value for outcome in Outcome)
