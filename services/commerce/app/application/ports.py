"""Application-layer ports (interfaces the use cases depend on, adapters implement)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Protocol, runtime_checkable

from app.domain.meal_plan import MealPlanSnapshot


@runtime_checkable
class MealPlanProvider(Protocol):
    """Resolves an owned meal plan from the Dietary service (anti-corruption boundary).

    Implementations forward the caller's bearer token so Dietary performs the ownership check;
    a plan that is missing or not owned resolves to ``None``. Transport/upstream failures raise
    :class:`~app.domain.errors.MealPlanUnavailableError`.
    """

    def fetch(self, plan_id: str, *, bearer_token: str) -> MealPlanSnapshot | None: ...


@runtime_checkable
class SlotInventory(Protocol):
    """How many bookings each dark-kitchen delivery window already holds for a day (COM-302).

    Availability subtracts these counts from each window's capacity to decide what is still
    bookable. The mapping is keyed by delivery window (the same strings the service area schedules);
    a window that is absent from the mapping is treated as having no bookings. The persistent,
    reservation-backed implementation arrives in COM-304 — until then availability is served by the
    empty inventory below, so every window shows its full capacity.
    """

    def booked_counts(self, zip_code: str, delivery_date: date) -> Mapping[str, int]: ...


class EmptySlotInventory:
    """A :class:`SlotInventory` that reports no bookings — every window is fully open.

    The default until slot reservation (COM-304) provides a persistent booking store; it is a pure
    null object, so it is safe to share as a module-level singleton.
    """

    def booked_counts(self, zip_code: str, delivery_date: date) -> Mapping[str, int]:
        return {}
