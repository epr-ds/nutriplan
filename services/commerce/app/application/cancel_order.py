"""COM-107 use case: cancel one of the caller's orders.

A thin write-side application service over the :class:`~app.domain.repositories.OrderRepository`
port. The order is loaded owner-scoped, so an unknown id and another user's order are both
``None`` and raise :class:`OrderNotFoundError` (a ``404`` at the edge, no enumeration). The domain
then decides whether the order may be cancelled: :meth:`Order.cancel` raises
:class:`IllegalOrderTransitionError` (a ``409``) once the order has been dispatched or is terminal.
The cancelled order is persisted via :meth:`OrderRepository.update` and returned.
"""

from __future__ import annotations

from app.application.commands import CancelOrderCommand
from app.domain.errors import OrderNotFoundError
from app.domain.order import Order
from app.domain.repositories import OrderRepository


class CancelOrderService:
    """Cancels an order owned by the caller, enforcing the lifecycle guards (COM-107)."""

    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    def cancel(self, command: CancelOrderCommand) -> Order:
        order = self._orders.get(command.order_id, user_id=command.user_id)
        if order is None:
            raise OrderNotFoundError(command.order_id)
        order.cancel()
        return self._orders.update(order)
