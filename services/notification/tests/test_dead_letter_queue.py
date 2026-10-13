"""The dead-letter queue, asserted against both adapters (NTF-204, AC2).

Parametrized over the in-memory and Redis queues for the same reason the store suites are,
with rather more at stake: by the time an event reaches this queue it has been acked, so the
entry here is the *only* remaining copy. An in-process stand-in that accepted a park the
durable one would have dropped, or listed entries in the other order, would let the CLI and
every runbook built on it pass in CI and mislead an operator during an incident.
"""

from __future__ import annotations

import json

import pytest

from app.events.consumer import DeliveredEvent
from app.events.dead_letter import DeadLetter, DeadLetterQueue, summarize
from tests.conftest import TEST_DLQ_CAPACITY

ENVELOPE = {
    "schemaVersion": 1,
    "id": "evt-1",
    "type": "order.confirmed",
    "occurredAt": "2026-07-12T21:00:00+00:00",
    "data": {"orderId": "o-1", "userId": "u-1"},
}


def payload(event_id: str = "evt-1", **overrides: object) -> str:
    """The envelope as commerce publishes it, under a chosen id."""
    return json.dumps({**ENVELOPE, "id": event_id, **overrides})


def delivery(delivery_id: str, *, attempt: int = 5, body: str | None = None) -> DeliveredEvent:
    """A delivery as the consumer hands it to the dispatcher."""
    return DeliveredEvent(
        delivery_id=delivery_id,
        payload=body if body is not None else payload(),
        attempt=attempt,
    )


def park_many(queue: DeadLetterQueue, count: int, *, prefix: str = "d") -> list[str]:
    """Park ``count`` entries in order, returning their delivery ids oldest-first."""
    ids = [f"{prefix}-{index}" for index in range(count)]
    for index, delivery_id in enumerate(ids):
        queue.park(delivery(delivery_id, body=payload(f"evt-{index}")), reason=f"reason {index}")
    return ids


class TestParking:
    def test_a_parked_delivery_can_be_read_back(self, dead_letter_queue: DeadLetterQueue) -> None:
        dead_letter_queue.park(delivery("d-1"), reason="handler rejected it")

        entry = dead_letter_queue.get("d-1")

        assert entry is not None
        assert entry.delivery_id == "d-1"
        assert entry.reason == "handler rejected it"

    def test_the_payload_is_kept_verbatim(self, dead_letter_queue: DeadLetterQueue) -> None:
        """The bytes are the evidence -- a re-serialised rendering loses what made it broken."""
        raw = '{"schemaVersion": 1, "type": "order.confirmed",  "trailing": "  spaces  " }'
        dead_letter_queue.park(delivery("d-1", body=raw), reason="nope")

        entry = dead_letter_queue.get("d-1")

        assert entry is not None
        assert entry.payload == raw

    def test_the_attempt_count_is_kept(self, dead_letter_queue: DeadLetterQueue) -> None:
        """How many tries it burned is the first thing an operator asks about a parked event."""
        dead_letter_queue.park(delivery("d-1", attempt=5), reason="budget exhausted")

        entry = dead_letter_queue.get("d-1")

        assert entry is not None
        assert entry.attempt == 5

    def test_the_type_and_event_id_are_summarised(self, dead_letter_queue: DeadLetterQueue) -> None:
        """So listing a hundred entries does not mean re-parsing a hundred payloads."""
        dead_letter_queue.park(delivery("d-1", body=payload("evt-9")), reason="nope")

        entry = dead_letter_queue.get("d-1")

        assert entry is not None
        assert (entry.event_type, entry.event_id) == ("order.confirmed", "evt-9")

    def test_an_unparseable_payload_is_still_parked(
        self, dead_letter_queue: DeadLetterQueue
    ) -> None:
        """The entries most worth keeping are the ones that could not be read."""
        dead_letter_queue.park(delivery("d-1", body="{not json"), reason="malformed")

        entry = dead_letter_queue.get("d-1")

        assert entry is not None
        assert entry.payload == "{not json"
        assert (entry.event_type, entry.event_id) == (None, None)

    def test_an_unknown_delivery_id_is_absent_rather_than_an_error(
        self, dead_letter_queue: DeadLetterQueue
    ) -> None:
        assert dead_letter_queue.get("never-parked") is None

    def test_parking_the_same_delivery_twice_keeps_one_entry(
        self, dead_letter_queue: DeadLetterQueue
    ) -> None:
        """Two rows for one message would double the depth NTF-706 alerts on."""
        dead_letter_queue.park(delivery("d-1"), reason="first")
        dead_letter_queue.park(delivery("d-1"), reason="second")

        assert dead_letter_queue.depth() == 1
        entry = dead_letter_queue.get("d-1")
        assert entry is not None and entry.reason == "second"


class TestListing:
    def test_an_empty_queue_lists_nothing(self, dead_letter_queue: DeadLetterQueue) -> None:
        assert list(dead_letter_queue.list()) == []

    def test_entries_come_back_newest_first(self, dead_letter_queue: DeadLetterQueue) -> None:
        """During an incident the useful entries are the ones failing now."""
        park_many(dead_letter_queue, 3)

        listed = [entry.delivery_id for entry in dead_letter_queue.list()]

        assert listed == ["d-2", "d-1", "d-0"]

    def test_a_limit_caps_the_page(self, dead_letter_queue: DeadLetterQueue) -> None:
        park_many(dead_letter_queue, 4)

        listed = [entry.delivery_id for entry in dead_letter_queue.list(limit=2)]

        assert listed == ["d-3", "d-2"]

    def test_an_offset_pages_through(self, dead_letter_queue: DeadLetterQueue) -> None:
        park_many(dead_letter_queue, 4)

        listed = [entry.delivery_id for entry in dead_letter_queue.list(limit=2, offset=2)]

        assert listed == ["d-1", "d-0"]

    def test_a_zero_limit_returns_nothing_rather_than_everything(
        self, dead_letter_queue: DeadLetterQueue
    ) -> None:
        """An off-by-one that dumped the whole queue into a terminal is a bad way to find out."""
        park_many(dead_letter_queue, 3)

        assert list(dead_letter_queue.list(limit=0)) == []

    def test_an_offset_past_the_end_is_empty(self, dead_letter_queue: DeadLetterQueue) -> None:
        park_many(dead_letter_queue, 2)

        assert list(dead_letter_queue.list(offset=50)) == []


class TestDepth:
    def test_an_empty_queue_has_no_depth(self, dead_letter_queue: DeadLetterQueue) -> None:
        assert dead_letter_queue.depth() == 0

    def test_depth_counts_the_parked_entries(self, dead_letter_queue: DeadLetterQueue) -> None:
        park_many(dead_letter_queue, 3)

        assert dead_letter_queue.depth() == 3

    def test_depth_is_read_not_accumulated(self, dead_letter_queue: DeadLetterQueue) -> None:
        """A parks-minus-removes counter drifts; this must reflect what is actually there."""
        park_many(dead_letter_queue, 3)
        dead_letter_queue.remove("d-1")

        assert dead_letter_queue.depth() == 2


class TestRemoval:
    def test_removing_an_entry_reports_that_it_was_there(
        self, dead_letter_queue: DeadLetterQueue
    ) -> None:
        dead_letter_queue.park(delivery("d-1"), reason="nope")

        assert dead_letter_queue.remove("d-1") is True
        assert dead_letter_queue.get("d-1") is None

    def test_removing_an_absent_entry_reports_that_it_was_not(
        self, dead_letter_queue: DeadLetterQueue
    ) -> None:
        """The replayer relies on this to tell "drained" from "someone else got there first"."""
        assert dead_letter_queue.remove("never-parked") is False

    def test_removal_leaves_the_other_entries_alone(
        self, dead_letter_queue: DeadLetterQueue
    ) -> None:
        park_many(dead_letter_queue, 3)

        dead_letter_queue.remove("d-1")

        assert [entry.delivery_id for entry in dead_letter_queue.list()] == ["d-2", "d-0"]


class TestPurge:
    def test_purging_empties_the_queue(self, dead_letter_queue: DeadLetterQueue) -> None:
        park_many(dead_letter_queue, 3)

        discarded = dead_letter_queue.purge()

        assert discarded == 3
        assert dead_letter_queue.depth() == 0
        assert list(dead_letter_queue.list()) == []

    def test_purging_an_empty_queue_discards_nothing(
        self, dead_letter_queue: DeadLetterQueue
    ) -> None:
        assert dead_letter_queue.purge() == 0

    def test_the_queue_still_works_after_a_purge(self, dead_letter_queue: DeadLetterQueue) -> None:
        """A purge must clear the index, not delete it in a way that breaks the next park."""
        park_many(dead_letter_queue, 2)
        dead_letter_queue.purge()

        dead_letter_queue.park(delivery("d-new"), reason="after the purge")

        assert dead_letter_queue.depth() == 1
        assert [entry.delivery_id for entry in dead_letter_queue.list()] == ["d-new"]


class TestTheQueueIsBounded:
    def test_it_stops_growing_at_its_capacity(self, dead_letter_queue: DeadLetterQueue) -> None:
        """One producer emitting a bad payload in a loop must not become a memory incident."""
        park_many(dead_letter_queue, TEST_DLQ_CAPACITY + 3)

        assert dead_letter_queue.depth() == TEST_DLQ_CAPACITY

    def test_eviction_drops_the_oldest(self, dead_letter_queue: DeadLetterQueue) -> None:
        """Current failures are what an incident needs; the first one is still in the log."""
        park_many(dead_letter_queue, TEST_DLQ_CAPACITY + 2)

        remaining = {entry.delivery_id for entry in dead_letter_queue.list(limit=50)}

        assert "d-0" not in remaining
        assert "d-1" not in remaining
        assert f"d-{TEST_DLQ_CAPACITY + 1}" in remaining

    def test_an_evicted_entry_is_gone_by_id_too(self, dead_letter_queue: DeadLetterQueue) -> None:
        """Not merely unlisted -- the record itself must go, or the cap bounds nothing."""
        park_many(dead_letter_queue, TEST_DLQ_CAPACITY + 1)

        assert dead_letter_queue.get("d-0") is None


class TestParkingNeverRaises:
    """Inherited from NTF-201's port contract and worth restating with the wider surface:
    ``park`` runs on the dispatcher's error path. A queue that raised would fail the
    handling of a failure -- the delivery would go back to pending and be retried forever
    on the strength of a fault in the machinery meant to stop the retrying."""

    def test_a_storage_failure_is_swallowed(self) -> None:
        from app.events.redis_dead_letter import RedisDeadLetterQueue

        class BrokenClient:
            def set(self, *args: object, **kwargs: object) -> None:
                raise ConnectionError("redis went away")

            def zadd(self, *args: object, **kwargs: object) -> None:
                raise ConnectionError("redis went away")

        queue = RedisDeadLetterQueue(BrokenClient())  # type: ignore[arg-type]

        queue.park(delivery("d-1"), reason="nope")  # must not raise

    def test_the_payload_reaches_the_log_even_when_storage_fails(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The log line is the only part of parking that cannot itself fail."""
        from app.events.redis_dead_letter import RedisDeadLetterQueue

        class BrokenClient:
            def set(self, *args: object, **kwargs: object) -> None:
                raise ConnectionError("redis went away")

        with caplog.at_level("ERROR"):
            RedisDeadLetterQueue(BrokenClient()).park(  # type: ignore[arg-type]
                delivery("d-1", body=payload("evt-lost")), reason="nope"
            )

        assert "evt-lost" in caplog.text


class TestTheSummary:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('{"type": "order.confirmed", "id": "evt-1"}', ("order.confirmed", "evt-1")),
            ("{not json", (None, None)),
            ("[1, 2, 3]", (None, None)),
            ('"a bare string"', (None, None)),
            ('{"type": 7, "id": []}', (None, None)),
            ('{"type": "   ", "id": "evt-1"}', (None, "evt-1")),
            ("{}", (None, None)),
        ],
    )
    def test_it_reads_what_it_can_and_never_raises(
        self, raw: str, expected: tuple[str | None, str | None]
    ) -> None:
        """It runs over payloads whose defining property is that parsing them failed."""
        assert summarize(raw) == expected


class TestTheEntry:
    def test_it_exposes_the_delivery_fields_it_wraps(self) -> None:
        entry = DeadLetter.of(delivery("d-1", attempt=3), reason="nope")

        assert (entry.delivery_id, entry.attempt, entry.payload) == ("d-1", 3, payload())

    def test_it_is_immutable(self) -> None:
        """Entries are handed to the CLI and the replayer; neither may edit the evidence."""
        entry = DeadLetter.of(delivery("d-1"), reason="nope")

        with pytest.raises((AttributeError, TypeError)):
            entry.reason = "something else"  # type: ignore[misc]
