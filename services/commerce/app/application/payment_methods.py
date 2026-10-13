"""COM-207 use cases: manage the caller's saved (tokenized) payment methods.

A thin application service over the :class:`~app.domain.repositories.PaymentMethodRepository` port
covering the three operations the story needs — list, add and delete — each scoped to the
authenticated caller. Constructing the :class:`~app.domain.payment_method.SavedPaymentMethod`
enforces the domain invariants (non-blank token, well-formed ``last4``/expiry); the repository
enforces owner-scoping, so deleting an unknown *or* another user's method is an indistinguishable
:class:`~app.domain.errors.PaymentMethodNotFoundError` (rendered ``404`` — no enumeration).
"""

from __future__ import annotations

from app.application.commands import AddPaymentMethodCommand, DeletePaymentMethodCommand
from app.application.queries import ListPaymentMethodsQuery
from app.domain.errors import PaymentMethodNotFoundError
from app.domain.payment_method import SavedPaymentMethod
from app.domain.repositories import PaymentMethodRepository


class PaymentMethodService:
    """Lists, adds and deletes a user's saved payment methods (COM-207)."""

    def __init__(self, methods: PaymentMethodRepository) -> None:
        self._methods = methods

    def list(self, query: ListPaymentMethodsQuery) -> list[SavedPaymentMethod]:
        return self._methods.list_for_user(query.user_id)

    def add(self, command: AddPaymentMethodCommand) -> SavedPaymentMethod:
        method = SavedPaymentMethod(
            user_id=command.user_id,
            type=command.type,
            token=command.token,
            brand=command.brand,
            last4=command.last4,
            exp_month=command.exp_month,
            exp_year=command.exp_year,
        )
        return self._methods.add(method)

    def delete(self, command: DeletePaymentMethodCommand) -> None:
        deleted = self._methods.delete(command.payment_method_id, user_id=command.user_id)
        if not deleted:
            raise PaymentMethodNotFoundError(command.payment_method_id)
