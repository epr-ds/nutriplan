"""Composition root / dependency wiring for the API layer.

FastAPI's ``Depends`` is used as a lightweight DI container: each provider builds one collaborator
and declares what it needs, so handlers receive fully-assembled services and never new up their own
dependencies. Tests swap any layer via ``app.dependency_overrides``.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.adapters.http_meal_plan_provider import HttpMealPlanProvider
from app.adapters.in_memory_kitchen_queue import InMemoryKitchenQueue
from app.adapters.kitchen_webhook_verifier import KitchenWebhookVerifier
from app.application.cancel_order import CancelOrderService
from app.application.create_order import CreateOrderService
from app.application.dark_kitchen_availability import CheckDarkKitchenAvailabilityService
from app.application.get_order import GetOrderService
from app.application.idempotency import IdempotencyStore
from app.application.list_orders import ListOrdersService
from app.application.payment_methods import PaymentMethodService
from app.application.ports import (
    KitchenQueue,
    MealPlanProvider,
    SlotInventory,
    SlotReservationStore,
)
from app.application.process_kitchen_webhook import ProcessKitchenWebhookService
from app.application.process_payment_webhook import ProcessPaymentWebhookService
from app.application.reserve_slot import ReserveDeliverySlotService
from app.application.route_to_kitchen import KitchenRouter
from app.core.config import settings
from app.core.principal import Principal
from app.core.security import InvalidTokenError, JwtTokenVerifier, TokenVerifier
from app.db.base import get_db
from app.domain.enums import FulfillmentType
from app.domain.fulfillment import DarkKitchenServiceArea
from app.domain.money import Money
from app.domain.pricing import DeliveryFeeSchedule, MealTypePriceBook, OrderPricer
from app.domain.repositories import OrderRepository, PaymentMethodRepository
from app.events.factory import build_event_publisher
from app.events.publisher import EventPublisher
from app.payments.factory import build_payment_provider
from app.payments.provider import PaymentProvider
from app.repositories.sql_idempotency_store import SqlIdempotencyStore
from app.repositories.sql_order_repository import SqlOrderRepository
from app.repositories.sql_payment_method_repository import SqlPaymentMethodRepository
from app.repositories.sql_slot_reservation_store import SqlSlotReservationStore

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


@lru_cache(maxsize=1)
def get_token_verifier() -> TokenVerifier:
    """Build the (cached) access-token verifier backed by Identity's JWKS endpoint."""
    jwks_client = jwt.PyJWKClient(settings.identity_jwks_url)
    return JwtTokenVerifier(
        key_resolver=jwks_client,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )


def _require_credentials(
    credentials: HTTPAuthorizationCredentials | None,
) -> HTTPAuthorizationCredentials:
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> Principal:
    """Resolve the authenticated caller from a bearer token or raise ``401``."""
    creds = _require_credentials(credentials)
    try:
        return verifier.verify(creds.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Expose the raw bearer token so it can be forwarded to Dietary (token relay)."""
    return _require_credentials(credentials).credentials


def get_order_repository(db: DbSession) -> OrderRepository:
    """Provide the SQL-backed order repository bound to the request session."""
    return SqlOrderRepository(db)


def get_payment_method_repository(db: DbSession) -> PaymentMethodRepository:
    """Provide the SQL-backed saved-payment-method repository bound to the request session."""
    return SqlPaymentMethodRepository(db)


def get_idempotency_store(db: DbSession) -> IdempotencyStore:
    """Provide the SQL-backed idempotency store bound to the request session (COM-209)."""
    return SqlIdempotencyStore(db)


def get_meal_plan_provider() -> MealPlanProvider:
    """Provide the HTTP meal-plan provider (anti-corruption layer over Dietary)."""
    return HttpMealPlanProvider(
        base_url=settings.dietary_base_url, timeout=settings.http_timeout_seconds
    )


@lru_cache(maxsize=1)
def get_order_pricer() -> OrderPricer:
    """Build the (cached) pricing engine from configured per-serving rates and delivery fees."""
    price_book = MealTypePriceBook(
        rates={
            "breakfast": Money(settings.price_per_serving_breakfast),
            "lunch": Money(settings.price_per_serving_lunch),
            "dinner": Money(settings.price_per_serving_dinner),
            "snack": Money(settings.price_per_serving_snack),
        },
        default_rate=Money(settings.price_per_serving_default),
    )
    delivery_fees = DeliveryFeeSchedule(
        fees={
            FulfillmentType.DARK_KITCHEN: Money(settings.delivery_fee_dark_kitchen),
            FulfillmentType.GROCERY_DELIVERY: Money(settings.delivery_fee_grocery_delivery),
            FulfillmentType.PICKUP: Money(settings.delivery_fee_pickup),
        },
        free_delivery_threshold=Money(settings.free_delivery_threshold),
    )
    return OrderPricer(price_book, delivery_fees, currency=settings.default_currency)


@lru_cache(maxsize=1)
def get_event_publisher() -> EventPublisher:
    """Build the (cached) domain-event publisher: a Redis stream in prod, in-process for dev/CI."""
    return build_event_publisher(settings)


@lru_cache(maxsize=1)
def get_payment_provider() -> PaymentProvider:
    """Build the (cached) config-selected payment provider (Stripe/Conekta; fake for dev/CI)."""
    return build_payment_provider(settings)


@lru_cache(maxsize=1)
def get_kitchen_queue() -> KitchenQueue:
    """Build the (cached) kitchen queue: an in-process recorder for dev/CI (COM-303).

    A durable kitchen integration (an HTTP call, or a stream a kitchen consumes) replaces this
    behind the ``KitchenQueue`` port without touching the routing use case.
    """
    return InMemoryKitchenQueue()


def get_kitchen_router(
    queue: Annotated[KitchenQueue, Depends(get_kitchen_queue)],
) -> KitchenRouter:
    """Build the router that hands confirmed dark-kitchen orders to the queue (COM-303)."""
    return KitchenRouter(queue)


@lru_cache(maxsize=1)
def get_kitchen_webhook_verifier() -> KitchenWebhookVerifier:
    """Build the (cached) verifier for inbound kitchen status webhooks (COM-303)."""
    return KitchenWebhookVerifier(settings.kitchen_webhook_secret.get_secret_value())


def _split_csv(raw: str) -> tuple[str, ...]:
    """Split a comma-separated config value into a tuple of trimmed, non-empty entries."""
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@lru_cache(maxsize=1)
def get_dark_kitchen_service_area() -> DarkKitchenServiceArea:
    """Build the (cached) dark-kitchen coverage/schedule/capacity policy from config (COM-302)."""
    return DarkKitchenServiceArea(
        served_zip_prefixes=_split_csv(settings.dark_kitchen_service_zip_prefixes),
        time_slots=_split_csv(settings.dark_kitchen_time_slots),
        slot_capacity=settings.dark_kitchen_slot_capacity,
    )


def get_slot_reservation_store(db: DbSession) -> SlotReservationStore:
    """Provide the SQL-backed dark-kitchen slot reservation store, request-scoped (COM-304).

    Not cached: it holds the per-request :class:`Session`, so reserving/releasing commits atomically
    with the order it accompanies (create) or the cancellation that frees it.
    """
    return SqlSlotReservationStore(db)


def get_slot_inventory(
    store: Annotated[SlotReservationStore, Depends(get_slot_reservation_store)],
) -> SlotInventory:
    """Provide dark-kitchen slot booking counts, now reflecting real reservations (COM-304).

    The reservation store doubles as the read-side inventory, so availability (COM-302) subtracts
    genuine bookings from each window's capacity rather than always showing it fully open.
    """
    return store


def get_reserve_slot_service(
    service_area: Annotated[DarkKitchenServiceArea, Depends(get_dark_kitchen_service_area)],
    store: Annotated[SlotReservationStore, Depends(get_slot_reservation_store)],
) -> ReserveDeliverySlotService:
    """Build the dark-kitchen slot reserve/release use case for create and cancel (COM-304)."""
    return ReserveDeliverySlotService(service_area, store)


def get_create_order_service(
    orders: Annotated[OrderRepository, Depends(get_order_repository)],
    meal_plans: Annotated[MealPlanProvider, Depends(get_meal_plan_provider)],
    pricer: Annotated[OrderPricer, Depends(get_order_pricer)],
    publisher: Annotated[EventPublisher, Depends(get_event_publisher)],
    payments: Annotated[PaymentProvider, Depends(get_payment_provider)],
    idempotency: Annotated[IdempotencyStore, Depends(get_idempotency_store)],
    kitchen_router: Annotated[KitchenRouter, Depends(get_kitchen_router)],
    slot_reservations: Annotated[ReserveDeliverySlotService, Depends(get_reserve_slot_service)],
) -> CreateOrderService:
    return CreateOrderService(
        orders,
        meal_plans,
        pricer,
        publisher,
        payments,
        idempotency,
        kitchen_router,
        slot_reservations,
    )


def get_list_orders_service(
    orders: Annotated[OrderRepository, Depends(get_order_repository)],
) -> ListOrdersService:
    return ListOrdersService(orders)


def get_get_order_service(
    orders: Annotated[OrderRepository, Depends(get_order_repository)],
) -> GetOrderService:
    return GetOrderService(orders)


def get_cancel_order_service(
    orders: Annotated[OrderRepository, Depends(get_order_repository)],
    payments: Annotated[PaymentProvider, Depends(get_payment_provider)],
    publisher: Annotated[EventPublisher, Depends(get_event_publisher)],
    slot_reservations: Annotated[ReserveDeliverySlotService, Depends(get_reserve_slot_service)],
) -> CancelOrderService:
    return CancelOrderService(orders, payments, publisher, slot_reservations)


def get_process_payment_webhook_service(
    orders: Annotated[OrderRepository, Depends(get_order_repository)],
    payments: Annotated[PaymentProvider, Depends(get_payment_provider)],
    publisher: Annotated[EventPublisher, Depends(get_event_publisher)],
    kitchen_router: Annotated[KitchenRouter, Depends(get_kitchen_router)],
    slot_reservations: Annotated[ReserveDeliverySlotService, Depends(get_reserve_slot_service)],
) -> ProcessPaymentWebhookService:
    return ProcessPaymentWebhookService(
        orders, payments, publisher, kitchen_router, slot_reservations
    )


def get_process_kitchen_webhook_service(
    orders: Annotated[OrderRepository, Depends(get_order_repository)],
    verifier: Annotated[KitchenWebhookVerifier, Depends(get_kitchen_webhook_verifier)],
    publisher: Annotated[EventPublisher, Depends(get_event_publisher)],
) -> ProcessKitchenWebhookService:
    return ProcessKitchenWebhookService(orders, verifier, publisher)


def get_payment_method_service(
    methods: Annotated[PaymentMethodRepository, Depends(get_payment_method_repository)],
) -> PaymentMethodService:
    return PaymentMethodService(methods)


def get_check_dark_kitchen_availability_service(
    service_area: Annotated[DarkKitchenServiceArea, Depends(get_dark_kitchen_service_area)],
    inventory: Annotated[SlotInventory, Depends(get_slot_inventory)],
) -> CheckDarkKitchenAvailabilityService:
    return CheckDarkKitchenAvailabilityService(service_area, inventory=inventory)


def get_current_user_id(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> uuid.UUID:
    """Resolve the caller's id from the verified token subject, or ``401`` if it is not a UUID."""
    try:
        return uuid.UUID(principal.user_id)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Token subject is not a valid user id"
        ) from exc


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]
BearerToken = Annotated[str, Depends(get_bearer_token)]
OrderRepositoryDep = Annotated[OrderRepository, Depends(get_order_repository)]
CreateOrderServiceDep = Annotated[CreateOrderService, Depends(get_create_order_service)]
ListOrdersServiceDep = Annotated[ListOrdersService, Depends(get_list_orders_service)]
GetOrderServiceDep = Annotated[GetOrderService, Depends(get_get_order_service)]
CancelOrderServiceDep = Annotated[CancelOrderService, Depends(get_cancel_order_service)]
PaymentMethodServiceDep = Annotated[PaymentMethodService, Depends(get_payment_method_service)]
DarkKitchenAvailabilityServiceDep = Annotated[
    CheckDarkKitchenAvailabilityService, Depends(get_check_dark_kitchen_availability_service)
]
PaymentWebhookServiceDep = Annotated[
    ProcessPaymentWebhookService, Depends(get_process_payment_webhook_service)
]
KitchenWebhookServiceDep = Annotated[
    ProcessKitchenWebhookService, Depends(get_process_kitchen_webhook_service)
]
