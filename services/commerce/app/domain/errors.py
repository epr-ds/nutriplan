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
