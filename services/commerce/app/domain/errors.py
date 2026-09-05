"""Commerce domain errors.

The domain and application layers stay transport-agnostic: they raise :class:`DomainError`
subclasses and :mod:`app.api.errors` owns the mapping onto HTTP status codes. A missing or
not-owned meal plan is deliberately indistinguishable (both :class:`MealPlanNotFoundError`) to avoid
resource enumeration.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all commerce domain/application errors."""


class OrderValidationError(DomainError):
    """A create-order request violates an invariant (e.g. grocery delivery without a provider)."""


class IllegalOrderTransitionError(DomainError):
    """An order was asked to move between lifecycle states the state machine forbids (COM-106).

    Maps to ``409 Conflict``: the request is well-formed but conflicts with the order's current
    state (e.g. cancelling an already-delivered order).
    """

    def __init__(self, current: object, target: object) -> None:
        super().__init__(f"cannot transition order from '{current}' to '{target}'")
        self.current = current
        self.target = target


class MealPlanNotFoundError(DomainError):
    """The referenced meal plan does not exist or is not owned by the caller."""

    def __init__(self, plan_id: object) -> None:
        super().__init__(f"meal plan {plan_id} not found")
        self.plan_id = plan_id


class OrderNotFoundError(DomainError):
    """The referenced order does not exist or is not owned by the caller.

    Unknown and not-owned are deliberately indistinguishable (both raise this) so one user can
    never probe for another user's order ids (COM-105 "no enumeration").
    """

    def __init__(self, order_id: object) -> None:
        super().__init__(f"order {order_id} not found")
        self.order_id = order_id


class MealPlanUnavailableError(DomainError):
    """The Dietary service could not be reached or returned an unexpected error."""


class PaymentDeclinedError(DomainError):
    """The payment provider declined the card charge (COM-202).

    Maps to ``402 Payment Required``: the request was well-formed but the charge did not succeed,
    so the order is not placed. Carries the provider's ``error_code`` (and optional message) so the
    client can tell the user why without our servers ever seeing the card itself.
    """

    def __init__(self, *, error_code: str, error_message: str | None = None) -> None:
        super().__init__(error_message or f"payment declined ({error_code})")
        self.error_code = error_code
        self.error_message = error_message


class WebhookVerificationError(DomainError):
    """A provider payment webhook could not be verified or understood (COM-206).

    Maps to ``400 Bad Request``: either the signature did not match the raw request body (so the
    event is not trusted to have come from the provider) or the verified body was malformed / has
    an event type we do not recognise. Nothing about the referenced order is revealed.
    """


class IdempotencyConflictError(DomainError):
    """The same ``Idempotency-Key`` was reused for a *different* request (COM-209).

    Maps to ``409 Conflict``: the key already identifies an earlier create-order request, so
    presenting it with a different body is a client mistake (a retry must be byte-for-byte the same
    request). Reusing the key with the *same* body is not an error — it replays the original order.
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"Idempotency-Key '{key}' was already used for a different request")
        self.key = key


class SlotUnavailableError(DomainError):
    """The chosen dark-kitchen delivery window has no remaining capacity (COM-304).

    Maps to ``409 Conflict``: the request is well-formed but the (area, day, window) the customer
    picked is already booked to its capacity, so the slot cannot be reserved. Reserving is atomic
    with creating the order, so a full slot places no order at all.
    """

    def __init__(self, *, zip_code: str, delivery_date: object, slot: str) -> None:
        super().__init__(f"delivery slot '{slot}' on {delivery_date} is fully booked")
        self.zip_code = zip_code
        self.delivery_date = delivery_date
        self.slot = slot


class PaymentMethodValidationError(DomainError):
    """A saved-payment-method request violates an invariant (COM-207).

    Maps to ``422 Unprocessable Entity`` (the :class:`DomainError` default): the request was
    well-formed JSON but a field is unusable — a blank token, a ``last4`` that is not four digits,
    or an out-of-range expiry.
    """


class PaymentMethodNotFoundError(DomainError):
    """The referenced saved payment method does not exist or is not owned by the caller (COM-207).

    As with orders, unknown and not-owned are deliberately indistinguishable (both raise this) so
    one user can never probe for another user's saved-method ids — the API renders it as ``404``.
    """

    def __init__(self, method_id: object) -> None:
        super().__init__(f"payment method {method_id} not found")
        self.method_id = method_id


class GroceryProviderUnavailableError(DomainError):
    """A grocery provider could not be reached or returned an unusable response (COM-402).

    The anti-corruption layer normalises every transport/upstream failure to this single domain
    error, so nothing above :class:`~app.grocery.adapter.GroceryProviderAdapter` depends on a
    provider's own exceptions; COM-407 layers per-provider circuit breakers and fallback over it.

    Maps to ``503 Service Unavailable`` when it reaches a route (COM-408): the request was perfectly
    valid, the provider simply cannot answer right now, so retrying later is the right move. The
    cross-provider search never surfaces it -- the fan-out skips the failing provider instead.
    """

    def __init__(self, provider_id: object, message: str | None = None) -> None:
        super().__init__(message or f"grocery provider {provider_id} is unavailable")
        self.provider_id = provider_id


class GroceryOrderNotPlacedError(DomainError):
    """A grocery status sync was asked for on an order that has no provider placement (COM-408).

    Maps to ``409 Conflict``: the order exists and belongs to the caller, but there is nothing to
    sync -- it is not a grocery order, or the provider has not accepted it yet, so no provider order
    reference exists to poll.
    """

    def __init__(self, order_id: object) -> None:
        super().__init__(f"order {order_id} has not been placed with a grocery provider")
        self.order_id = order_id
