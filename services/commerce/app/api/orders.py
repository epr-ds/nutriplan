"""Orders API router (COM-102)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import BearerToken, CreateOrderServiceDep, CurrentPrincipal
from app.api.schemas import CreateOrderRequest, OrderResponse
from app.application.commands import CreateOrderCommand

router = APIRouter(tags=["Orders"])


@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an order from a meal plan",
)
def create_order(
    body: CreateOrderRequest,
    principal: CurrentPrincipal,
    token: BearerToken,
    service: CreateOrderServiceDep,
) -> OrderResponse:
    """Turn one of the caller's meal plans into a PENDING order (COM-102).

    Ownership of ``mealPlanId`` is enforced by Dietary (the caller's token is forwarded); a missing
    or not-owned plan is ``404``, a ``grocery_delivery`` without ``providerId`` is ``422``, and an
    unreachable Dietary is ``503``. On success the created order is returned with ``201``.
    """
    try:
        user_id = uuid.UUID(principal.user_id)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Token subject is not a valid user id"
        ) from exc

    command = CreateOrderCommand(
        user_id=user_id,
        meal_plan_id=str(body.meal_plan_id),
        fulfillment_type=body.fulfillment_type,
        delivery_address=body.delivery_address.to_domain(),
        delivery_date=body.delivery_date,
        delivery_time_slot=body.delivery_time_slot,
        provider_id=body.provider_id,
        notes=body.notes,
    )
    order = service.create(command, bearer_token=token)
    return OrderResponse.from_order(order)
