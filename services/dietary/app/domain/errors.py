"""Domain errors for the Dietary Planning bounded context.

These represent violations of business rules (invariants) and are intentionally decoupled from
HTTP/transport concerns — the API layer maps :class:`DomainError` subclasses onto responses.
"""

from __future__ import annotations

from datetime import date


class DomainError(Exception):
    """Base class for violations of a domain invariant."""


class MealPlanDateRangeError(DomainError):
    """Raised when a meal plan's ``endDate`` falls before its ``startDate``."""

    def __init__(self, start_date: date, end_date: date) -> None:
        super().__init__(f"endDate ({end_date}) must be on or after startDate ({start_date})")
        self.start_date = start_date
        self.end_date = end_date
