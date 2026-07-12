"""Orders API router (COM-102 create, COM-104 list, COM-105 get, COM-107 cancel)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import (
    BearerToken,
    CancelOrderServiceDep,
    CreateOrderServiceDep,
    CurrentPrincipal,
    GetOrderServiceDep,
    ListOrdersServiceDep,
)
from app.api.schemas import CreateOrderRequest, OrderResponse
from app.application.commands import CancelOrderCommand, CreateOrderCommand
from app.application.queries import GetOrderQuery, ListOrdersQuery
from app.domain.enums import OrderStatus

router = APIRouter(tags=["Orders"])


def _principal_user_id(principal: CurrentPrincipal) -> uuid.UUID:
    """Resolve the authenticated caller's id, or ``401`` if the token subject is not a UUID."""
    try:
        return uuid.UUID(principal.user_id)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Token subject is not a valid user id"
        ) from exc


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
    command = CreateOrderCommand(
        user_id=_principal_user_id(principal),
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


@router.get(
    "/orders",
    response_model=list[OrderResponse],
    summary="List the current user's orders",
)
def list_orders(
    principal: CurrentPrincipal,
    service: ListOrdersServiceDep,
    status_filter: Annotated[OrderStatus | None, Query(alias="status")] = None,
    from_date: Annotated[date | None, Query(alias="fromDate")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[OrderResponse]:
    """Return the caller's orders newest-first, filtered by ``status``/``fromDate`` and paginated.

    Results are always scoped to the authenticated caller (COM-104). ``page`` is 1-based and
    ``limit`` is the page size (1–100); out-of-range values are rejected with ``422``.
    """
    query = ListOrdersQuery(
        user_id=_principal_user_id(principal),
        status=status_filter,
        from_date=from_date,
        page=page,
        limit=limit,
    )
    orders = service.list(query)
    return [OrderResponse.from_order(order) for order in orders]


@router.get(
    "/orders/{order_id}",
    response_model=OrderResponse,
    summary="Get one of the current user's orders",
)
def get_order(
    order_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: GetOrderServiceDep,
) -> OrderResponse:
    """Return the caller's order identified by ``orderId`` with full detail (COM-105).

    Reads are owner-scoped: an unknown id and another user's order are indistinguishable and both
    yield ``404`` (no enumeration). A malformed (non-UUID) ``orderId`` is rejected with ``422``.
    """
    query = GetOrderQuery(user_id=_principal_user_id(principal), order_id=order_id)
    order = service.get(query)
    return OrderResponse.from_order(order)


@router.post(
    "/orders/{order_id}/cancel",
    response_model=OrderResponse,
    summary="Cancel an order",
)
def cancel_order(
    order_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: CancelOrderServiceDep,
) -> OrderResponse:
    """Cancel the caller's order identified by ``orderId`` (COM-107).

    Cancellation is owner-scoped: an unknown id and another user's order both yield ``404`` (no
    enumeration, as with reads). An order may only be cancelled before dispatch; once it is
    ``in_transit`` or in a terminal state the lifecycle state machine refuses and this returns
    ``409``. On success the updated order is returned with ``200``.
    """
    command = CancelOrderCommand(user_id=_principal_user_id(principal), order_id=order_id)
    order = service.cancel(command)
    return OrderResponse.from_order(order)
