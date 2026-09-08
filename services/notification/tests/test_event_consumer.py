"""At-least-once delivery, asserted against both consumer adapters (NTF-201, AC1 + AC3).

Every test here runs twice: once against the in-process consumer and once against a real
Redis consumer group. That is the point. The in-process adapter exists to make dev and CI
work without a broker, and it is only worth having if it is *not* an easier world -- a
stand-in that quietly forgot to redeliver an unacked message would let the entire framework
pass here and lose events in production.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import pytest

from app.events.backoff import RetrySchedule
from app.events.memory import InMemoryEventConsumer
from app.events.redis_stream import PAYLOAD_FIELD, RedisStreamEventConsumer
from tests.conftest import (
    TEST_CONSUMER_GROUP,
    TEST_CONSUMER_NAME,
    EventBus,
    isolated_stream,
    require_redis_url,
)

EVENT = {
    "schemaVersion": 1,
    "id": "evt-1",
    "type": "order.confirmed",
    "occurredAt": "2026-07-12T21:00:00+00:00",
    "data": {"orderId": "o-1", "userId": "u-1"},
}


NO_BACKOFF = RetrySchedule(base_ms=0, jitter=0.0)
"""Everything pending is due immediately, so a test about redelivery is not also a test
about waiting. The schedule itself is exercised in test_event_backoff."""


def event(event_id: str) -> dict[str, object]:
    """The sample envelope under a distinct id, so a batch is distinguishable."""
    return {**EVENT, "id": event_id}


def ids(deliveries: object) -> list[str]:
    """The producer-assigned event ids of a batch, in delivery order."""
    return [json.loads(delivery.payload)["id"] for delivery in deliveries]  # type: ignore[union-attr]


class TestDelivery:
    def test_a_published_event_is_delivered(self, event_bus: EventBus) -> None:
        event_bus.publish(EVENT)

        delivered = event_bus.consumer.poll(count=10, block_ms=100)

        assert len(delivered) == 1
        assert json.loads(delivered[0].payload) == EVENT

    def test_the_payload_arrives_byte_for_byte(self, event_bus: EventBus) -> None:
        """Parked evidence is only useful if it is what was actually published."""
        raw = json.dumps(EVENT)
        event_bus.publish(raw)

        assert event_bus.consumer.poll(count=10, block_ms=100)[0].payload == raw

    def test_events_are_delivered_in_publication_order(self, event_bus: EventBus) -> None:
        event_bus.publish_all(event("a"), event("b"), event("c"))

        assert ids(event_bus.consumer.poll(count=10, block_ms=100)) == ["a", "b", "c"]

    def test_a_batch_is_capped_at_the_requested_count(self, event_bus: EventBus) -> None:
        event_bus.publish_all(event("a"), event("b"), event("c"))

        assert ids(event_bus.consumer.poll(count=2, block_ms=100)) == ["a", "b"]

    def test_the_next_poll_resumes_where_the_last_one_stopped(self, event_bus: EventBus) -> None:
        """The group's offset advances on delivery -- that is what makes replicas disjoint."""
        event_bus.publish_all(event("a"), event("b"), event("c"))

        event_bus.consumer.poll(count=2, block_ms=100)

        assert ids(event_bus.consumer.poll(count=10, block_ms=100)) == ["c"]

    def test_polling_an_empty_stream_returns_nothing(self, event_bus: EventBus) -> None:
        assert event_bus.consumer.poll(count=10, block_ms=50) == ()

    def test_a_delivered_event_is_not_delivered_again_by_a_later_poll(
        self, event_bus: EventBus
    ) -> None:
        """New-message delivery is once per group; redelivery only happens via reclaim."""
        event_bus.publish(EVENT)
        event_bus.consumer.poll(count=10, block_ms=100)

        assert event_bus.consumer.poll(count=10, block_ms=50) == ()

    def test_the_first_delivery_is_attempt_one(self, event_bus: EventBus) -> None:
        event_bus.publish(EVENT)

        assert event_bus.consumer.poll(count=10, block_ms=100)[0].attempt == 1

    def test_ensure_group_is_idempotent(self, event_bus: EventBus) -> None:
        """It runs on every worker start, and only the first one creates anything."""
        event_bus.consumer.ensure_group()
        event_bus.consumer.ensure_group()

        event_bus.publish(EVENT)

        assert len(event_bus.consumer.poll(count=10, block_ms=100)) == 1


class TestAtLeastOnce:
    """An unacked message must come back; an acked one must not."""

    def test_an_unacked_event_is_reclaimable(self, event_bus: EventBus) -> None:
        event_bus.publish(EVENT)
        event_bus.consumer.poll(count=10, block_ms=100)

        reclaimed = event_bus.consumer.reclaim(schedule=NO_BACKOFF, count=10).deliveries

        assert ids(reclaimed) == ["evt-1"]

    def test_an_acked_event_is_never_seen_again(self, event_bus: EventBus) -> None:
        event_bus.publish(EVENT)
        delivered = event_bus.consumer.poll(count=10, block_ms=100)

        event_bus.consumer.ack(delivered[0].delivery_id)

        assert event_bus.consumer.reclaim(schedule=NO_BACKOFF, count=10).deliveries == ()
        assert event_bus.consumer.poll(count=10, block_ms=50) == ()

    def test_reclaiming_increments_the_attempt(self, event_bus: EventBus) -> None:
        """The retry budget is counted by the broker, so it survives the consumer dying."""
        event_bus.publish(EVENT)
        event_bus.consumer.poll(count=10, block_ms=100)

        first = event_bus.consumer.reclaim(schedule=NO_BACKOFF, count=10).deliveries
        second = event_bus.consumer.reclaim(schedule=NO_BACKOFF, count=10).deliveries

        assert first[0].attempt == 2
        assert second[0].attempt == 3

    def test_an_event_still_being_worked_on_is_not_reclaimed(self, event_bus: EventBus) -> None:
        """Reclaiming a healthy in-flight message manufactures the duplicate NTF-103 suppresses."""
        event_bus.publish(EVENT)
        event_bus.consumer.poll(count=10, block_ms=100)

        batch = event_bus.consumer.reclaim(
            schedule=RetrySchedule(base_ms=60_000, jitter=0.0), count=10
        )

        assert batch.deliveries == ()

    def test_reclaim_finds_the_event_once_it_has_gone_idle(self, event_bus: EventBus) -> None:
        event_bus.publish(EVENT)
        event_bus.consumer.poll(count=10, block_ms=100)
        time.sleep(0.05)

        batch = event_bus.consumer.reclaim(schedule=RetrySchedule(base_ms=10, jitter=0.0), count=10)

        assert len(batch.deliveries) == 1

    def test_reclaim_is_capped_at_the_requested_count(self, event_bus: EventBus) -> None:
        event_bus.publish_all(event("a"), event("b"), event("c"))
        event_bus.consumer.poll(count=10, block_ms=100)

        assert len(event_bus.consumer.reclaim(schedule=NO_BACKOFF, count=2).deliveries) == 2

    def test_reclaim_on_a_clean_group_returns_nothing(self, event_bus: EventBus) -> None:
        """The overwhelmingly common case: nothing is stranded, so the sweep is cheap."""
        assert event_bus.consumer.reclaim(schedule=NO_BACKOFF, count=10).deliveries == ()

    def test_acking_an_unknown_id_is_a_no_op(self, event_bus: EventBus) -> None:
        """As ``XACK`` is -- a double ack after a retry must not become an error."""
        event_bus.consumer.ack("999999-0")

    def test_acking_twice_is_a_no_op(self, event_bus: EventBus) -> None:
        event_bus.publish(EVENT)
        delivered = event_bus.consumer.poll(count=10, block_ms=100)

        event_bus.consumer.ack(delivered[0].delivery_id)
        event_bus.consumer.ack(delivered[0].delivery_id)

        assert event_bus.consumer.reclaim(schedule=NO_BACKOFF, count=10).deliveries == ()

    def test_only_the_unacked_half_of_a_batch_comes_back(self, event_bus: EventBus) -> None:
        """The realistic crash: some of a batch settled, some did not."""
        event_bus.publish_all(event("a"), event("b"), event("c"))
        delivered = event_bus.consumer.poll(count=10, block_ms=100)
        event_bus.consumer.ack(delivered[0].delivery_id)
        event_bus.consumer.ack(delivered[2].delivery_id)

        assert ids(event_bus.consumer.reclaim(schedule=NO_BACKOFF, count=10).deliveries) == ["b"]


class TestANewGroupStartsAtTheEndOfTheStream:
    """``XGROUP CREATE ... $``: the backlog is skipped on purpose.

    Starting at ``0`` reads as the lose-nothing option and is the opposite -- first deploy
    against a stream holding a month of commerce traffic would notify every user about every
    order they have ever placed. These build their own consumer rather than using the
    ``event_bus`` fixture, which creates its group up front precisely so other tests do not
    trip over this.
    """

    def test_the_in_memory_group_skips_what_was_published_before_it_existed(self) -> None:
        consumer = InMemoryEventConsumer()
        consumer.publish(event("before"))

        consumer.ensure_group()
        consumer.publish(event("after"))

        assert ids(consumer.poll(count=10, block_ms=0)) == ["after"]

    def test_the_redis_group_skips_what_was_published_before_it_existed(self) -> None:
        import redis

        client = redis.Redis.from_url(require_redis_url(), decode_responses=True)
        stream = isolated_stream()
        try:
            client.xadd(stream, {PAYLOAD_FIELD: json.dumps(event("before"))})

            consumer = RedisStreamEventConsumer(
                client,  # type: ignore[arg-type]
                stream=stream,
                group=TEST_CONSUMER_GROUP,
                consumer=TEST_CONSUMER_NAME,
            )
            consumer.ensure_group()
            client.xadd(stream, {PAYLOAD_FIELD: json.dumps(event("after"))})

            assert ids(consumer.poll(count=10, block_ms=100)) == ["after"]
        finally:
            client.delete(stream)
            client.close()

    def test_the_group_is_created_even_when_the_stream_does_not_exist_yet(self) -> None:
        """``MKSTREAM``: consumer and producer can be deployed in either order."""
        import redis

        client = redis.Redis.from_url(require_redis_url(), decode_responses=True)
        stream = isolated_stream()
        try:
            consumer = RedisStreamEventConsumer(
                client,  # type: ignore[arg-type]
                stream=stream,
                group=TEST_CONSUMER_GROUP,
                consumer=TEST_CONSUMER_NAME,
            )
            consumer.ensure_group()

            assert client.exists(stream)
            client.xadd(stream, {PAYLOAD_FIELD: json.dumps(EVENT)})
            assert len(consumer.poll(count=10, block_ms=100)) == 1
        finally:
            client.delete(stream)
            client.close()


class TestTheRedisAdapterSpecifically:
    """Behaviour that only exists once a real broker is involved."""

    @pytest.fixture
    def stream_client(self) -> Iterator[Any]:
        import redis

        client = redis.Redis.from_url(require_redis_url(), decode_responses=True)
        try:
            yield client
        finally:
            client.close()

    def test_competing_consumers_in_one_group_get_disjoint_slices(self, stream_client: Any) -> None:
        """The reason for a consumer group at all: replicas share the stream, not the work."""
        stream = isolated_stream()
        try:
            first = RedisStreamEventConsumer(
                stream_client,  # type: ignore[arg-type]
                stream=stream,
                group=TEST_CONSUMER_GROUP,
                consumer="replica-1",
            )
            second = RedisStreamEventConsumer(
                stream_client,  # type: ignore[arg-type]
                stream=stream,
                group=TEST_CONSUMER_GROUP,
                consumer="replica-2",
            )
            first.ensure_group()
            second.ensure_group()

            for name in ("a", "b", "c", "d"):
                stream_client.xadd(stream, {PAYLOAD_FIELD: json.dumps(event(name))})

            got = ids(first.poll(count=2, block_ms=100)) + ids(second.poll(count=2, block_ms=100))

            assert sorted(got) == ["a", "b", "c", "d"]
        finally:
            stream_client.delete(stream)

    def test_one_replica_reclaims_what_another_left_pending(self, stream_client: Any) -> None:
        """The crash-recovery path: a dead pod's messages must not be stranded forever."""
        stream = isolated_stream()
        try:
            dead = RedisStreamEventConsumer(
                stream_client,  # type: ignore[arg-type]
                stream=stream,
                group=TEST_CONSUMER_GROUP,
                consumer="replica-dead",
            )
            alive = RedisStreamEventConsumer(
                stream_client,  # type: ignore[arg-type]
                stream=stream,
                group=TEST_CONSUMER_GROUP,
                consumer="replica-alive",
            )
            dead.ensure_group()
            stream_client.xadd(stream, {PAYLOAD_FIELD: json.dumps(EVENT)})
            dead.poll(count=10, block_ms=100)

            reclaimed = alive.reclaim(schedule=NO_BACKOFF, count=10).deliveries

            assert ids(reclaimed) == ["evt-1"]
            assert reclaimed[0].attempt == 2
        finally:
            stream_client.delete(stream)

    def test_an_entry_without_a_payload_field_is_delivered_as_its_raw_fields(
        self, stream_client: Any
    ) -> None:
        """So a hand-written ``XADD`` is parked *with its contents*, not silently skipped."""
        stream = isolated_stream()
        try:
            consumer = RedisStreamEventConsumer(
                stream_client,  # type: ignore[arg-type]
                stream=stream,
                group=TEST_CONSUMER_GROUP,
                consumer=TEST_CONSUMER_NAME,
            )
            consumer.ensure_group()
            stream_client.xadd(stream, {"body": "oops"})

            delivered = consumer.poll(count=10, block_ms=100)

            assert len(delivered) == 1
            assert json.loads(delivered[0].payload) == {"body": "oops"}
        finally:
            stream_client.delete(stream)

    def test_a_pending_entry_deleted_from_the_stream_is_acked_not_redelivered(
        self, stream_client: Any
    ) -> None:
        """A tombstone in the pending list would otherwise be reclaimed on every sweep."""
        stream = isolated_stream()
        try:
            consumer = RedisStreamEventConsumer(
                stream_client,  # type: ignore[arg-type]
                stream=stream,
                group=TEST_CONSUMER_GROUP,
                consumer=TEST_CONSUMER_NAME,
            )
            consumer.ensure_group()
            entry_id = stream_client.xadd(stream, {PAYLOAD_FIELD: json.dumps(EVENT)})
            consumer.poll(count=10, block_ms=100)
            stream_client.xdel(stream, entry_id)

            assert consumer.reclaim(schedule=NO_BACKOFF, count=10).deliveries == ()
            assert consumer.reclaim(schedule=NO_BACKOFF, count=10).deliveries == ()
        finally:
            stream_client.delete(stream)


class TestTheInMemoryAdapterSpecifically:
    def test_it_reports_how_many_deliveries_are_unsettled(self) -> None:
        """Used by the worker tests to assert nothing was left behind."""
        consumer = InMemoryEventConsumer()
        consumer.ensure_group()
        consumer.publish(EVENT)
        delivered = consumer.poll(count=10, block_ms=0)

        assert consumer.pending_count == 1

        consumer.ack(delivered[0].delivery_id)

        assert consumer.pending_count == 0

    def test_a_dict_is_serialized_the_way_the_real_publisher_does(self) -> None:
        """So a test writing a dict still exercises the JSON round-trip production runs."""
        consumer = InMemoryEventConsumer()
        consumer.ensure_group()
        consumer.publish(EVENT)

        assert consumer.poll(count=10, block_ms=0)[0].payload == json.dumps(EVENT)
