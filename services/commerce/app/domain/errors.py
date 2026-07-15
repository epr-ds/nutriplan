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


class IdempotencyConflictError(DomainError):
    """The same ``Idempotency-Key`` was reused for a *different* request (COM-209).

    Maps to ``409 Conflict``: the key already identifies an earlier create-order request, so
    presenting it with a different body is a client mistake (a retry must be byte-for-byte the same
    request). Reusing the key with the *same* body is not an error — it replays the original order.
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"Idempotency-Key '{key}' was already used for a different request")
        self.key = key
