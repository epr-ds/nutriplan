"""Domain errors for the Dietary Planning bounded context.

These represent business-rule outcomes raised by the domain/application layers and are intentionally
decoupled from HTTP/transport concerns — the API layer maps :class:`DomainError` subclasses onto
responses (invariant violations default to ``422``; specific subclasses may map elsewhere).
"""

from __future__ import annotations

from datetime import date


class DomainError(Exception):
    """Base class for errors raised by the domain/application layers and surfaced by the API."""


class MealPlanDateRangeError(DomainError):
    """Raised when a meal plan's ``endDate`` falls before its ``startDate``."""

    def __init__(self, start_date: date, end_date: date) -> None:
        super().__init__(f"endDate ({end_date}) must be on or after startDate ({start_date})")
        self.start_date = start_date
        self.end_date = end_date


class MealPlanNotFoundError(DomainError):
    """Raised when the requested meal plan does not exist for the caller (maps to ``404``).

    A missing plan and a plan owned by a *different* user are deliberately indistinguishable, so the
    API never reveals the existence of data the caller does not own.
    """

    def __init__(self, plan_id: str) -> None:
        super().__init__(f"Meal plan {plan_id} was not found")
        self.plan_id = plan_id


class IllegalStateTransitionError(DomainError):
    """Raised when a meal plan is moved between lifecycle states that the machine forbids (``409``).

    The transition is structurally impossible given the plan's *current* status (e.g. reopening a
    completed plan), as opposed to a transition whose preconditions merely aren't met yet.
    """

    def __init__(self, current: object, target: object) -> None:
        super().__init__(f"Cannot transition meal plan from '{current}' to '{target}'")
        self.current = current
        self.target = target


class EmptyMealPlanActivationError(DomainError):
    """Raised when activating a meal plan that has no meals (maps to the default ``422``).

    Unlike :class:`IllegalStateTransitionError`, the ``draft -> active`` transition is itself legal;
    it is the activation *precondition* (at least one meal) that is unmet, so the request is
    well-formed but cannot be processed.
    """

    def __init__(self, plan_id: str) -> None:
        super().__init__("A meal plan must have at least one meal before it can be activated")
        self.plan_id = plan_id
