"""The order-progress mark, as a contract both adapters must satisfy (NTF-202, AC3).

Every test here runs twice -- once in-process, once against a live Redis. That is the point:
this store is the only thing standing between a user and being told their order is being
prepared after they have eaten it, and a double that quietly behaved differently from the
real thing would prove nothing about production.

The monotonicity tests are the ones to preserve. A store that merely *remembers* the last
status is easy to write and useless: it would happily record a stale status over a later one
and then confirm to the consumer that the order had gone backwards.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

import pytest

from app.domain.order_status import NO_PROGRESS, OrderStatus, progress_of
from app.domain.repositories import OrderProgressStore

OrderProgressFactory = Callable[..., OrderProgressStore]

FORWARD = [
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.IN_TRANSIT,
    OrderStatus.DELIVERED,
]


def order() -> str:
    """A fresh order id, so no two tests can collide on a shared key."""
    return str(uuid.uuid4())


class TestAnUntouchedOrder:
    def test_it_has_made_no_progress(self, order_progress: OrderProgressFactory) -> None:
        assert order_progress().progress_of(order()) == NO_PROGRESS

    def test_its_first_status_is_always_forward(self, order_progress: OrderProgressFactory) -> None:
        """Including ``cancelled``, which can be an order's very first newsworthy event."""
        store = order_progress()

        assert store.advance(order(), OrderStatus.CANCELLED) is True

    def test_orders_do_not_share_a_mark(self, order_progress: OrderProgressFactory) -> None:
        store = order_progress()
        first, second = order(), order()

        store.advance(first, OrderStatus.DELIVERED)

        assert store.progress_of(second) == NO_PROGRESS


class TestMovingForward:
    def test_the_mark_records_the_status_reached(
        self, order_progress: OrderProgressFactory
    ) -> None:
        store = order_progress()
        order_id = order()

        store.advance(order_id, OrderStatus.PREPARING)

        assert store.progress_of(order_id) == progress_of(OrderStatus.PREPARING)

    def test_each_step_of_the_happy_path_moves_it(
        self, order_progress: OrderProgressFactory
    ) -> None:
        store = order_progress()
        order_id = order()

        moved = [store.advance(order_id, status) for status in FORWARD]

        assert moved == [True, True, True, True]
        assert store.progress_of(order_id) == progress_of(OrderStatus.DELIVERED)

    def test_a_skipped_status_still_moves_it(self, order_progress: OrderProgressFactory) -> None:
        """Commerce may not publish every intermediate step, and a gap is not an error."""
        store = order_progress()
        order_id = order()

        store.advance(order_id, OrderStatus.CONFIRMED)

        assert store.advance(order_id, OrderStatus.DELIVERED) is True


class TestRefusingToGoBackwards:
    def test_the_same_status_twice_does_not_move_it(
        self, order_progress: OrderProgressFactory
    ) -> None:
        store = order_progress()
        order_id = order()
        store.advance(order_id, OrderStatus.IN_TRANSIT)

        assert store.advance(order_id, OrderStatus.IN_TRANSIT) is False

    @pytest.mark.parametrize("stale", [OrderStatus.CONFIRMED, OrderStatus.PREPARING])
    def test_an_earlier_status_does_not_move_it(
        self, order_progress: OrderProgressFactory, stale: OrderStatus
    ) -> None:
        """The scenario the whole store exists for: a late event from an earlier step."""
        store = order_progress()
        order_id = order()
        store.advance(order_id, OrderStatus.IN_TRANSIT)

        assert store.advance(order_id, stale) is False

    def test_a_refused_advance_leaves_the_mark_alone(
        self, order_progress: OrderProgressFactory
    ) -> None:
        """A refusal that still wrote would let a stale event undo the real position."""
        store = order_progress()
        order_id = order()
        store.advance(order_id, OrderStatus.DELIVERED)

        store.advance(order_id, OrderStatus.CONFIRMED)

        assert store.progress_of(order_id) == progress_of(OrderStatus.DELIVERED)

    def test_replaying_the_whole_sequence_moves_nothing(
        self, order_progress: OrderProgressFactory
    ) -> None:
        """An NTF-204 replay of an entire order's events must be inert."""
        store = order_progress()
        order_id = order()
        for status in FORWARD:
            store.advance(order_id, status)

        assert [store.advance(order_id, s) for s in FORWARD] == [False] * len(FORWARD)


class TestCancellation:
    def test_it_moves_the_mark_from_any_earlier_status(
        self, order_progress: OrderProgressFactory
    ) -> None:
        store = order_progress()
        order_id = order()
        store.advance(order_id, OrderStatus.PREPARING)

        assert store.advance(order_id, OrderStatus.CANCELLED) is True

    @pytest.mark.parametrize("stale", FORWARD)
    def test_nothing_earlier_survives_it(
        self, order_progress: OrderProgressFactory, stale: OrderStatus
    ) -> None:
        """Announcing "being prepared" after "cancelled" is the worst thing this can do."""
        store = order_progress()
        order_id = order()
        store.advance(order_id, OrderStatus.CANCELLED)

        assert store.advance(order_id, stale) is False


class TestTheWindow:
    def test_the_mark_does_not_outlive_its_ttl(self, order_progress: OrderProgressFactory) -> None:
        """It bounds memory: an order that ended is not worth remembering forever.

        Timed against the real clock rather than an injected one, because a fake clock is
        exactly the kind of shortcut that would let the two adapters disagree here -- Redis
        expires keys on its own schedule and cannot be handed a stub. One second of test
        time buys the assurance that both really forget.
        """
        store = order_progress(ttl_seconds=1)
        order_id = order()
        store.advance(order_id, OrderStatus.DELIVERED)
        time.sleep(1.2)

        assert store.progress_of(order_id) == NO_PROGRESS

    def test_an_expired_mark_lets_the_order_move_again(
        self, order_progress: OrderProgressFactory
    ) -> None:
        """The guard is a window, not a permanent record -- and the dedupe store, whose
        window is independent, is what still covers a replay arriving after this one."""
        store = order_progress(ttl_seconds=1)
        order_id = order()
        store.advance(order_id, OrderStatus.DELIVERED)
        time.sleep(1.2)

        assert store.advance(order_id, OrderStatus.CONFIRMED) is True

    def test_movement_keeps_the_mark_alive(self, order_progress: OrderProgressFactory) -> None:
        """A long-lived order must not expire mid-lifecycle from its first status."""
        store = order_progress(ttl_seconds=3_600)
        order_id = order()
        store.advance(order_id, OrderStatus.CONFIRMED)
        store.advance(order_id, OrderStatus.IN_TRANSIT)

        assert store.progress_of(order_id) == progress_of(OrderStatus.IN_TRANSIT)

    def test_a_zero_ttl_is_clamped_rather_than_disabling_the_guard(
        self, order_progress: OrderProgressFactory
    ) -> None:
        """A misconfigured zero must not silently turn off out-of-order protection."""
        store = order_progress(ttl_seconds=0)
        order_id = order()

        store.advance(order_id, OrderStatus.DELIVERED)

        assert store.progress_of(order_id) == progress_of(OrderStatus.DELIVERED)


class TestTheStorePortIsSatisfied:
    def test_the_adapter_is_recognised_as_the_port(
        self, order_progress: OrderProgressFactory
    ) -> None:
        assert isinstance(order_progress(), OrderProgressStore)
