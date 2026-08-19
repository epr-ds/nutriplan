"""COM-107 use case: cancel one of the caller's orders, refunding a paid one (COM-208).

A thin write-side application service over the :class:`~app.domain.repositories.OrderRepository`
port. The order is loaded owner-scoped, so an unknown id and another user's order are both
``None`` and raise :class:`OrderNotFoundError` (a ``404`` at the edge, no enumeration). The domain
then decides whether the order may be cancelled: :meth:`Order.cancel` raises
:class:`IllegalOrderTransitionError` (a ``409``) once the order has been dispatched or is terminal.

When the cancelled order carried a **captured payment** (a card charge, COM-202, or a settled async
method, COM-206), the money is returned through the :class:`~app.payments.provider.PaymentProvider`
port (COM-208): a full refund of the total by default, or a partial refund when the command supplies
an ``refund_amount``. The provider's ``refund_id`` and the amount returned are recorded on the order
before it is persisted via :meth:`OrderRepository.update` and returned.
"""

from __future__ import annotations

from app.application.commands import CancelOrderCommand
from app.application.reserve_slot import ReserveDeliverySlotService
from app.domain.errors import OrderNotFoundError
from app.domain.money import Money
from app.domain.order import Order
from app.domain.payment import PaymentRefundRequest
from app.domain.repositories import OrderRepository
from app.events.publisher import EventPublisher
from app.payments.provider import PaymentProvider


class CancelOrderService:
    """Cancels an order owned by the caller and refunds it when it was paid (COM-107/208).

    On success it publishes the resulting ``order.status_changed`` event to the bus (COM-109).
    """

    def __init__(
        self,
        orders: OrderRepository,
        payments: PaymentProvider,
        publisher: EventPublisher,
        slot_reservations: ReserveDeliverySlotService | None = None,
    ) -> None:
        self._orders = orders
        self._payments = payments
        self._publisher = publisher
        self._slot_reservations = slot_reservations

    def cancel(self, command: CancelOrderCommand) -> Order:
        order = self._orders.get(command.order_id, user_id=command.user_id)
        if order is None:
            raise OrderNotFoundError(command.order_id)
        # Cancel first so the lifecycle guard (a 409 for a dispatched/terminal order) runs before we
        # ever touch the provider; only a legitimately cancelled order is refunded.
        order.cancel()
        # Release any dark-kitchen slot the order held so the freed capacity is bookable again
        # (COM-304). Idempotent and a no-op for an order that never held one; the delete is
        # committed atomically by orders.update() below.
        if self._slot_reservations is not None:
            self._slot_reservations.release_for(order.id)
        self._refund_if_paid(command, order)
        persisted = self._orders.update(order)
        # Best-effort publish after the cancellation is committed; drain from the aggregate we hold.
        for event in order.pull_events():
            self._publisher.publish(event)
        return persisted

    def _refund_if_paid(self, command: CancelOrderCommand, order: Order) -> None:
        """Refund the cancelled order through the provider when it carried a captured payment.

        A full refund (``refund_amount`` unset) returns the whole total; a set ``refund_amount``
        makes it partial. An order that was never paid is simply cancelled — unless the caller
        explicitly asked to refund one, which :meth:`Order.validate_refund` surfaces as a conflict.
        The provider's ``refund_id`` and the amount returned are recorded on the order.
        """
        requested = (
            Money(command.refund_amount, order.total.currency)
            if command.refund_amount is not None
            else None
        )
        if requested is None and not order.can_refund:
            return
        amount = order.validate_refund(requested)
        result = self._payments.refund(
            PaymentRefundRequest(
                charge_id=order.payment_charge_id or "",
                amount=amount,
                reference=str(order.id),
            )
        )
        order.record_refund(refund_id=result.refund_id, amount=result.amount)
