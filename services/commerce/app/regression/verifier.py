"""Grade the commerce regression corpus against the production use cases (HRD-905 follow-up).

The release gate executes the commerce regression corpus -- the golden order / payment / lifecycle
scenarios the beta fix -> re-release loop burns down on -- through the production application
services in-process (no DB, no network), so a regression in idempotency, payment settlement,
cancellation refunds, slot booking or webhook settlement fails the gate before release.

Each corpus :class:`CommerceCase` maps to a scenario handler that drives the real use cases and
collects the failures; the :class:`RegressionReport` is the GATE -- any failure means a commerce
regression, and the runner fails the release on it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.application.cancel_order import CancelOrderService
from app.application.commands import CancelOrderCommand, CreateOrderCommand
from app.application.create_order import CreateOrderService
from app.application.place_grocery_order import GroceryOrderPlacer
from app.application.process_payment_webhook import ProcessPaymentWebhookService
from app.application.reserve_slot import ReserveDeliverySlotService
from app.domain.address import Address
from app.domain.enums import FulfillmentType, OrderStatus, PaymentMethodType
from app.domain.errors import PaymentDeclinedError, SlotUnavailableError
from app.domain.fulfillment import DarkKitchenServiceArea
from app.domain.meal_plan import MealPlanSnapshot, PlannedMeal
from app.domain.order import Order
from app.domain.payment import PaymentStatus
from app.events.memory import InMemoryEventPublisher
from app.grocery.adapter import (
    GroceryOrderPlacement,
    GroceryOrderRequest,
    GrocerySearchQuery,
    GrocerySearchResult,
)
from app.grocery.fake import FakeGroceryProviderAdapter
from app.payments.fake import FakePaymentProvider
from app.regression.case import CommerceCase, CommerceCaseOutcome
from app.regression.corpus import load_commerce_cases
from tests.fakes import (
    FakeMealPlanProvider,
    InMemoryIdempotencyStore,
    InMemoryOrderRepository,
    make_test_pricer,
)

_BEARER = "bearer-corpus"
_USER = uuid.uuid4()
_ADDRESS = Address(
    street="Av. Reforma 100",
    city="CDMX",
    state="CDMX",
    zip_code="06600",
    country="MX",
)
_PLAN = "plan-corpus"
_AT = datetime(2026, 11, 2, 13, 0)


class _Harness:
    """In-process production wiring shared by the commerce release-gate scenarios."""

    def __init__(self) -> None:
        self.provider = FakePaymentProvider(webhook_secret="corpus-webhook-secret")
        self.orders = InMemoryOrderRepository()
        self.service = CreateOrderService(
            orders=self.orders,
            meal_plans=FakeMealPlanProvider(
                MealPlanSnapshot(
                    plan_id=_PLAN,
                    meals=[
                        PlannedMeal(
                            meal_type="lunch", servings=Decimal("2"), recipe_name="Lentil soup"
                        )
                    ],
                )
            ),
            pricer=make_test_pricer(),
            publisher=InMemoryEventPublisher(),
            payments=self.provider,
            idempotency=InMemoryIdempotencyStore(),
        )

    def create_order(
        self,
        *,
        fulfillment_type: FulfillmentType = FulfillmentType.DARK_KITCHEN,
        provider_id: str | None = None,
        payment_method_type: PaymentMethodType | None = None,
        payment_token: str | None = None,
        idempotency_key: str | None = None,
        planned_meal: PlannedMeal | None = None,
    ) -> Order:
        if planned_meal is not None:
            self.service._meal_plans = FakeMealPlanProvider(
                MealPlanSnapshot(plan_id=_PLAN, meals=[planned_meal])
            )
        command = CreateOrderCommand(
            user_id=_USER,
            meal_plan_id=_PLAN,
            fulfillment_type=fulfillment_type,
            delivery_address=_ADDRESS,
            delivery_date=date(2026, 11, 2),
            delivery_time_slot="12:00-13:00",
            provider_id=provider_id,
            payment_method_type=payment_method_type,
            payment_token=payment_token,
        )
        return self.service.create(command, bearer_token=_BEARER, idempotency_key=idempotency_key)


class _InMemorySlotReservationStore:
    """In-process slot reservation store satisfying the :class:`SlotReservationStore` port."""

    def __init__(self) -> None:
        self._bookings: dict[tuple[str, date, str], list[uuid.UUID]] = {}

    def booked_counts(self, zip_code: str, delivery_date: date) -> dict[str, int]:
        return {
            slot: len(order_ids)
            for (code, day, slot), order_ids in self._bookings.items()
            if code == zip_code and day == delivery_date
        }

    def reserve(
        self, *, zip_code: str, delivery_date: date, slot: str, order_id: uuid.UUID, capacity: int
    ) -> None:
        key = (zip_code, delivery_date, slot)
        order_ids = self._bookings.setdefault(key, [])
        if len(order_ids) >= capacity:
            raise SlotUnavailableError(f"slot {slot} at {zip_code} on {delivery_date} is full")
        order_ids.append(order_id)

    def release(self, *, order_id: uuid.UUID) -> None:
        for order_ids in self._bookings.values():
            if order_id in order_ids:
                order_ids.remove(order_id)


class _FailingGroceryAdapter:
    """A grocery provider adapter whose placement always fails (to exercise the fallback)."""

    @property
    def provider_id(self) -> str:
        return "grocery-primary"

    def search(self, query: GrocerySearchQuery) -> GrocerySearchResult:
        return GrocerySearchResult(provider_id=self.provider_id, products=())

    def place_order(self, request: GroceryOrderRequest) -> GroceryOrderPlacement:
        raise RuntimeError("grocery provider unavailable")

    def get_order_status(self, external_order_id: str) -> object:
        raise RuntimeError("grocery provider unavailable")


@dataclass(frozen=True, slots=True)
class RegressionReport:
    """The verdict over a whole commerce corpus: per-case outcomes and a single gate flag."""

    outcomes: tuple[CommerceCaseOutcome, ...]

    @property
    def ok(self) -> bool:
        """Whether every case passed -- the value the release gate keys on."""
        return all(outcome.ok for outcome in self.outcomes)

    @property
    def failures(self) -> tuple[str, ...]:
        """Every failure across the corpus, each prefixed with its case name."""
        return tuple(
            f"{outcome.name}: {failure}"
            for outcome in self.outcomes
            for failure in outcome.failures
        )


def _verify_order_creation_idempotent(case: CommerceCase) -> tuple[str, ...]:
    harness = _Harness()
    first = harness.create_order(
        payment_method_type=PaymentMethodType.CREDIT_CARD,
        payment_token="tok_visa_secret",
        idempotency_key="idem-corpus-order",
    )
    second = harness.create_order(
        payment_method_type=PaymentMethodType.CREDIT_CARD,
        payment_token="tok_visa_secret",
        idempotency_key="idem-corpus-order",
    )
    failures: list[str] = []
    if second.id != first.id:
        failures.append(
            "retry with a reused idempotency key created order "
            f"{second.id} instead of replaying {first.id}"
        )
    if len(harness.provider.charges) != 1:
        failures.append(
            f"idempotent retry charged the payment provider {len(harness.provider.charges)} times"
        )
    return tuple(failures)


def _verify_payment_success_flow(case: CommerceCase) -> tuple[str, ...]:
    harness = _Harness()
    order = harness.create_order(
        payment_method_type=PaymentMethodType.CREDIT_CARD, payment_token="tok_visa_secret"
    )
    failures: list[str] = []
    if order.status is not OrderStatus.CONFIRMED:
        failures.append(f"successful card charge left the order in {order.status.value}")
    if order.payment_status is not PaymentStatus.SUCCEEDED:
        failures.append(
            "successful card charge did not record payment_status SUCCEEDED "
            f"(got {order.payment_status})"
        )
    if not harness.provider.charges:
        failures.append("successful card charge captured no provider charge")
    return tuple(failures)


def _verify_payment_failure_retry(case: CommerceCase) -> tuple[str, ...]:
    harness = _Harness()
    declined = CreateOrderCommand(
        user_id=_USER,
        meal_plan_id=_PLAN,
        fulfillment_type=FulfillmentType.DARK_KITCHEN,
        delivery_address=_ADDRESS,
        delivery_date=date(2026, 11, 2),
        delivery_time_slot="12:00-13:00",
        payment_method_type=PaymentMethodType.CREDIT_CARD,
        payment_token="tok_decline_001",
    )
    try:
        harness.service.create(declined, bearer_token=_BEARER)
    except PaymentDeclinedError:
        pass
    else:
        return ("the declined card token unexpectedly produced a successful charge",)
    retried = harness.create_order(
        payment_method_type=PaymentMethodType.CREDIT_CARD,
        payment_token="tok_visa_secret",
        idempotency_key="idem-corpus-retry",
    )
    failures: list[str] = []
    if retried.payment_status is not PaymentStatus.SUCCEEDED:
        failures.append("retry after a decline did not settle the payment")
    return tuple(failures)


def _verify_order_cancellation_refund(case: CommerceCase) -> tuple[str, ...]:
    harness = _Harness()
    order = harness.create_order(
        payment_method_type=PaymentMethodType.CREDIT_CARD, payment_token="tok_visa_secret"
    )
    canceller = CancelOrderService(
        orders=harness.orders,
        payments=harness.provider,
        publisher=InMemoryEventPublisher(),
    )
    persisted = canceller.cancel(
        CancelOrderCommand(user_id=_USER, order_id=order.id, refund_amount=None)
    )
    failures: list[str] = []
    if persisted.status is not OrderStatus.CANCELLED:
        failures.append(f"cancelling a paid order left it in {persisted.status.value}")
    if not harness.provider.refunds:
        failures.append("cancelling a paid order did not refund through the provider")
    return tuple(failures)


def _verify_slot_reservation_concurrency(case: CommerceCase) -> tuple[str, ...]:
    store = _InMemorySlotReservationStore()
    reservations = ReserveDeliverySlotService(
        DarkKitchenServiceArea(served_zip_prefixes=("066",), time_slots=("12:00-13:00",)), store
    )
    for _ in range(2):
        order = Order(
            user_id=_USER,
            fulfillment_type=FulfillmentType.DARK_KITCHEN,
            delivery_address=_ADDRESS,
            delivery_date=date(2026, 11, 2),
            delivery_time_slot="12:00-13:00",
            id=uuid.uuid4(),
        )
        reservations.reserve_for(order)
    failures: list[str] = []
    booked = store.booked_counts("06600", date(2026, 11, 2)).get("12:00-13:00", 0)
    if booked != 2:
        failures.append(f"two concurrent slot reservations left {booked} booked for the window")
    return tuple(failures)


def _verify_grocery_provider_fallback(case: CommerceCase) -> tuple[str, ...]:
    harness = _Harness()
    order = harness.create_order(
        fulfillment_type=FulfillmentType.GROCERY_DELIVERY,
        provider_id="grocery-a",
        payment_method_type=PaymentMethodType.CREDIT_CARD,
        payment_token="tok_visa_secret",
        planned_meal=PlannedMeal(meal_type="milk", servings=Decimal("1"), recipe_name="Milk"),
    )
    placeable = GroceryOrderPlacer(
        orders=harness.orders,
        adapters={
            "grocery-a": _FailingGroceryAdapter(),
            "grocery-b": FakeGroceryProviderAdapter("grocery-b"),
        },
        publisher=InMemoryEventPublisher(),
    )
    if placeable.place(order) is not None:
        return ("the primary grocery adapter unexpectedly placed the order",)
    order.provider_id = "grocery-b"
    placed = placeable.place(order)
    failures: list[str] = []
    if placed is None:
        failures.append("the fallback grocery adapter did not place the confirmed order")
    return tuple(failures)


def _verify_voucher_application(case: CommerceCase) -> tuple[str, ...]:
    harness = _Harness()
    order = harness.create_order(payment_method_type=PaymentMethodType.OXXO)
    failures: list[str] = []
    if order.payment_voucher_reference is None:
        failures.append("an OXXO voucher was issued but not applied to the order")
    if order.payment_status is not PaymentStatus.PENDING:
        failures.append(f"a voucher-backed order should stay pending (got {order.payment_status})")
    return tuple(failures)


def _verify_webhook_retry_delivery(case: CommerceCase) -> tuple[str, ...]:
    harness = _Harness()
    pending = harness.create_order(payment_method_type=PaymentMethodType.OXXO)
    payload = json.dumps(
        {
            "type": "payment.confirmed",
            "data": {"reference": str(pending.id), "charge_id": "fake_ch_corpus"},
        }
    ).encode("utf-8")
    signature = hmac.new(b"corpus-webhook-secret", payload, hashlib.sha256).hexdigest()
    settler = ProcessPaymentWebhookService(
        orders=harness.orders,
        payments=harness.provider,
        publisher=InMemoryEventPublisher(),
    )
    settled = settler.process(payload=payload, signature=signature)
    failures: list[str] = []
    if settled.status is not OrderStatus.CONFIRMED:
        failures.append(f"a confirmed provider webhook left the order in {settled.status.value}")
    redelivered = settler.process(payload=payload, signature=signature)
    if redelivered.status is not OrderStatus.CONFIRMED:
        failures.append("a redelivered provider webhook moved the order again")
    return tuple(failures)


_VERIFIERS: dict[str, Callable[[CommerceCase], tuple[str, ...]]] = {
    "order-creation-idempotent": _verify_order_creation_idempotent,
    "payment-success-flow": _verify_payment_success_flow,
    "payment-failure-retry": _verify_payment_failure_retry,
    "order-cancellation-refund": _verify_order_cancellation_refund,
    "slot-reservation-concurrency": _verify_slot_reservation_concurrency,
    "grocery-provider-fallback": _verify_grocery_provider_fallback,
    "voucher-application": _verify_voucher_application,
    "webhook-retry-delivery": _verify_webhook_retry_delivery,
}


class CommerceRegressionVerifier:
    """Check a golden commerce corpus against the production use cases."""

    def verify(self, cases: tuple[CommerceCase, ...] | None = None) -> RegressionReport:
        """Run every case and collect the outcomes into a report."""
        cases = cases if cases is not None else load_commerce_cases()
        return RegressionReport(tuple(self._verify_case(case) for case in cases))

    def _verify_case(self, case: CommerceCase) -> CommerceCaseOutcome:
        handler = _VERIFIERS.get(case.name)
        if handler is None:
            return CommerceCaseOutcome(
                name=case.name,
                failures=(f"no commerce regression scenario for case {case.name!r}",),
            )
        return CommerceCaseOutcome(name=case.name, failures=handler(case))
