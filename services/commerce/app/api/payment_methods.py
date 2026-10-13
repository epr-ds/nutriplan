"""Saved payment-methods API router (COM-207: list, add, delete).

Every route is scoped to the authenticated caller and the stored provider token is never returned —
only a method's id and non-sensitive display metadata cross the wire.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUserId, PaymentMethodServiceDep
from app.api.schemas import PaymentMethodResponse, SavePaymentMethodRequest
from app.application.commands import AddPaymentMethodCommand, DeletePaymentMethodCommand
from app.application.queries import ListPaymentMethodsQuery

router = APIRouter(tags=["Payments"], prefix="/payment-methods")


@router.get("", response_model=list[PaymentMethodResponse], summary="List saved payment methods")
def list_payment_methods(
    user_id: CurrentUserId, service: PaymentMethodServiceDep
) -> list[PaymentMethodResponse]:
    """Return the caller's saved payment methods, newest first (COM-207).

    Results are always scoped to the authenticated caller; the stored provider token is never
    included — only each method's id and non-sensitive display metadata.
    """
    methods = service.list(ListPaymentMethodsQuery(user_id=user_id))
    return [PaymentMethodResponse.from_method(method) for method in methods]


@router.post(
    "",
    response_model=PaymentMethodResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a tokenized payment method",
)
def add_payment_method(
    body: SavePaymentMethodRequest, user_id: CurrentUserId, service: PaymentMethodServiceDep
) -> PaymentMethodResponse:
    """Store a tokenized payment method for the caller and return it (COM-207).

    The request carries a provider ``token`` produced by on-device tokenization — never a PAN. A
    blank token or a malformed ``last4``/expiry is ``422``. On success the saved method is returned
    with ``201`` (without the stored token).
    """
    command = AddPaymentMethodCommand(
        user_id=user_id,
        type=body.type,
        token=body.token,
        brand=body.brand,
        last4=body.last4,
        exp_month=body.exp_month,
        exp_year=body.exp_year,
    )
    return PaymentMethodResponse.from_method(service.add(command))


@router.delete(
    "/{payment_method_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a saved payment method",
)
def delete_payment_method(
    payment_method_id: uuid.UUID, user_id: CurrentUserId, service: PaymentMethodServiceDep
) -> None:
    """Delete one of the caller's saved payment methods (COM-207).

    Owner-scoped: an unknown id and another user's method are indistinguishable and both yield
    ``404`` (no enumeration). On success the method is removed and ``204`` is returned.
    """
    service.delete(DeletePaymentMethodCommand(user_id=user_id, payment_method_id=payment_method_id))
