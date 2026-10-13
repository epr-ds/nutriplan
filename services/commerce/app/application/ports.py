"""Application-layer ports (interfaces the use cases depend on, adapters implement)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import date
from typing import Protocol, runtime_checkable

from app.domain.kitchen import KitchenTicket
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


@runtime_checkable
class SlotReservationStore(Protocol):
    """Persistent dark-kitchen slot bookings: the capacity write path behind availability (COM-304).

    A superset of :class:`SlotInventory` -- it also answers ``booked_counts`` (so it can serve
    availability directly, reflecting real bookings) and adds the two mutations that consume and
    release a window's daily capacity:

    * ``reserve`` atomically books one unit of a window's capacity for an order: it counts the
      window's existing bookings for ``(zip_code, delivery_date, slot)`` and, if that count has
      already reached ``capacity``, raises :class:`~app.domain.errors.SlotUnavailableError`;
      otherwise it records the reservation. It does **not** commit -- the reservation is made
      durable by the order it is created alongside, so a later failure in the same request (e.g. a
      declined payment) rolls the pending reservation back with it.
    * ``release`` deletes an order's reservation, freeing the capacity when the order is cancelled.
      Idempotent (a missing reservation is a no-op) and likewise does **not** commit.
    """

    def booked_counts(self, zip_code: str, delivery_date: date) -> Mapping[str, int]: ...

    def reserve(
        self,
        *,
        zip_code: str,
        delivery_date: date,
        slot: str,
        order_id: uuid.UUID,
        capacity: int,
    ) -> None: ...

    def release(self, *, order_id: uuid.UUID) -> None: ...


@runtime_checkable
class KitchenQueue(Protocol):
    """Where a confirmed dark-kitchen order is handed off to be cooked (COM-303).

    A single outbound port the routing use case depends on: given a :class:`KitchenTicket`, deliver
    it to a kitchen. Keeping it a port lets a real kitchen integration (an HTTP call or a durable
    stream a kitchen consumes) be one adapter among others, while an in-process adapter backs
    dev/CI and tests. Routing happens after the order is committed and is best-effort, so an
    implementation should be safe to call in the request path.
    """

    def route(self, ticket: KitchenTicket) -> None: ...
