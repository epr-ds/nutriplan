"""What an order status means, and how far along it is (NTF-202).

The ordering assertions here are the load-bearing ones. They read like restatements of the
data, and they are -- but the data is a policy decision (a cancelled order must never be
overtaken by a stale earlier status), and a policy nobody asserts is a policy the next
person edits by accident.
"""

from __future__ import annotations

import pytest

from app.domain.enums import NotificationType
from app.domain.order_status import (
    NO_PROGRESS,
    PROGRESS,
    OrderStatus,
    UnknownOrderStatus,
    notification_type_for,
    progress_of,
)


class TestTheVocabulary:
    def test_it_matches_the_statuses_commerce_publishes(self) -> None:
        """A copy of COM-106; drift here means events we silently cannot map."""
        assert {s.value for s in OrderStatus} == {
            "pending",
            "confirmed",
            "preparing",
            "in_transit",
            "delivered",
            "cancelled",
        }

    @pytest.mark.parametrize("status", list(OrderStatus))
    def test_every_status_has_a_rank(self, status: OrderStatus) -> None:
        """A status without a rank would raise mid-dispatch instead of being decided."""
        assert status in PROGRESS

    def test_parsing_accepts_the_wire_form(self) -> None:
        assert OrderStatus.parse("in_transit") is OrderStatus.IN_TRANSIT

    def test_parsing_tolerates_surrounding_whitespace(self) -> None:
        assert OrderStatus.parse("  delivered ") is OrderStatus.DELIVERED

    def test_parsing_is_idempotent(self) -> None:
        assert OrderStatus.parse(OrderStatus.PREPARING) is OrderStatus.PREPARING

    def test_an_unknown_status_is_not_a_value_error(self) -> None:
        """It must be distinguishable: ValueError would be retried, this is parked."""
        with pytest.raises(UnknownOrderStatus):
            OrderStatus.parse("refunded")

    def test_a_non_string_is_rejected_by_name(self) -> None:
        with pytest.raises(UnknownOrderStatus, match="must be a string"):
            OrderStatus.parse(7)

    def test_the_message_names_the_status_it_could_not_read(self) -> None:
        """The dead-letter reason is the only clue an operator gets."""
        with pytest.raises(UnknownOrderStatus, match="refunded"):
            OrderStatus.parse("refunded")


class TestWhatIsWorthTelling:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (OrderStatus.CONFIRMED, NotificationType.ORDER_CONFIRMED),
            (OrderStatus.PREPARING, NotificationType.ORDER_PREPARING),
            (OrderStatus.IN_TRANSIT, NotificationType.ORDER_IN_TRANSIT),
            (OrderStatus.DELIVERED, NotificationType.ORDER_DELIVERED),
            (OrderStatus.CANCELLED, NotificationType.ORDER_CANCELLED),
        ],
    )
    def test_each_newsworthy_status_maps_to_its_type(
        self, status: OrderStatus, expected: NotificationType
    ) -> None:
        assert notification_type_for(status) is expected

    def test_pending_is_understood_and_deliberately_silent(self) -> None:
        """The user is looking at the confirmation screen; this is not news."""
        assert notification_type_for(OrderStatus.PENDING) is None

    def test_silent_and_unrecognised_are_different_answers(self) -> None:
        """Collapsing them is how a new order status becomes a silent outage."""
        assert notification_type_for(OrderStatus.PENDING) is None
        with pytest.raises(UnknownOrderStatus):
            notification_type_for("refunded")

    def test_every_order_notification_type_is_reachable(self) -> None:
        """A type nothing can produce is dead weight in the preferences matrix."""
        produced = {notification_type_for(s) for s in OrderStatus} - {None}

        assert produced == {t for t in NotificationType if t.is_order_update}


class TestHowFarAlong:
    def test_the_happy_path_ranks_in_order(self) -> None:
        assert (
            progress_of(OrderStatus.PENDING)
            < progress_of(OrderStatus.CONFIRMED)
            < progress_of(OrderStatus.PREPARING)
            < progress_of(OrderStatus.IN_TRANSIT)
            < progress_of(OrderStatus.DELIVERED)
        )

    @pytest.mark.parametrize(
        "earlier",
        [
            OrderStatus.PENDING,
            OrderStatus.CONFIRMED,
            OrderStatus.PREPARING,
            OrderStatus.IN_TRANSIT,
            OrderStatus.DELIVERED,
        ],
    )
    def test_cancelled_outranks_everything(self, earlier: OrderStatus) -> None:
        """Once cancelled, no earlier status may ever be announced -- the whole reason
        the rank is a notification ordering rather than a copy of the state machine."""
        assert progress_of(OrderStatus.CANCELLED) > progress_of(earlier)

    def test_the_ranks_are_distinct(self) -> None:
        """Two statuses sharing a rank would let one silently suppress the other."""
        assert len(set(PROGRESS.values())) == len(PROGRESS)

    def test_an_unrecorded_order_ranks_below_every_status(self) -> None:
        """So a brand-new order's very first event is always forward movement."""
        assert all(NO_PROGRESS < rank for rank in PROGRESS.values())

    def test_the_table_cannot_be_edited_at_runtime(self) -> None:
        with pytest.raises(TypeError):
            PROGRESS[OrderStatus.CANCELLED] = 0  # type: ignore[index]


class TestTerminality:
    def test_delivered_and_cancelled_end_the_order(self) -> None:
        assert OrderStatus.DELIVERED.is_terminal
        assert OrderStatus.CANCELLED.is_terminal

    @pytest.mark.parametrize(
        "status",
        [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.IN_TRANSIT],
    )
    def test_everything_else_can_still_move(self, status: OrderStatus) -> None:
        assert not status.is_terminal
