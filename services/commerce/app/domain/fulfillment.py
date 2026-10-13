"""Dark-kitchen fulfillment domain (COM-301, COM-302).

A dark kitchen delivers prepared orders within a service area. This module models, as pure domain
logic, whether that area covers a given delivery postcode and which delivery windows it can still
accept an order for:

* :class:`DarkKitchenServiceArea` is the coverage + schedule + **capacity** policy — a zip is served
  when its postcode begins with one of the configured prefixes, every serviceable day offers the
  same set of delivery windows, and each window can hold up to ``slot_capacity`` bookings per day
  (COM-302). Availability reflects the *remaining* capacity: a window whose bookings have reached
  capacity is no longer offered.
* :class:`SlotAvailability` is the per-window capacity arithmetic (capacity minus bookings, floored
  at zero) — the "slot math" the availability decision is built on, unit-testable in isolation.
* :class:`DarkKitchenAvailability` is the immutable result the API projects onto
  ``AvailabilityResponse``.

Booking counts themselves live outside the domain (they are read through the ``SlotInventory``
application port, whose persistent writer arrives with slot reservation in COM-304). The domain only
does the arithmetic, so the availability rules stay unit-testable without HTTP or a database.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SlotAvailability:
    """Remaining capacity arithmetic for a single delivery window on a given day (COM-302).

    ``booked`` is how many orders that window already holds; ``remaining`` is the capacity left,
    floored at zero so an over-booked window never reports negative headroom, and a window is
    ``is_bookable`` only while some headroom remains.
    """

    slot: str
    capacity: int
    booked: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.capacity - max(0, self.booked))

    @property
    def is_bookable(self) -> bool:
        return self.remaining > 0


@dataclass(frozen=True)
class DarkKitchenAvailability:
    """Whether a dark kitchen serves a delivery area, and the windows it can deliver in.

    ``time_slots`` is empty whenever ``available`` is ``False`` — an area that is not served, or one
    whose every window is fully booked for the requested day, offers no windows — so callers never
    have to reconcile the two fields.
    """

    zip_code: str
    available: bool
    time_slots: tuple[str, ...] = ()


@dataclass(frozen=True)
class DarkKitchenServiceArea:
    """Coverage, daily schedule, and per-window capacity for dark-kitchen fulfillment (COM-302).

    Coverage is by Mexican postal-code (*código postal*) prefix: a postcode is served when it starts
    with any configured prefix, so a whole delegation/municipality can be covered by its leading
    digits. ``time_slots`` are the delivery windows offered on every serviceable day, and
    ``slot_capacity`` is how many orders each window can hold per day (the per-zone capacity). Only
    windows with remaining capacity are surfaced, and only for a serviceable request.
    """

    served_zip_prefixes: tuple[str, ...]
    time_slots: tuple[str, ...]
    slot_capacity: int = 20

    def check(
        self,
        zip_code: str,
        *,
        delivery_date: date | None = None,
        today: date | None = None,
        booked: Mapping[str, int] | None = None,
    ) -> DarkKitchenAvailability:
        """Decide availability for ``zip_code`` (optionally for a specific ``delivery_date``).

        The area must cover the postcode; additionally, when both a ``delivery_date`` and a
        ``today`` reference are given, a date already in the past is not serviceable (a kitchen
        cannot deliver in the past). For a serviceable request only windows with remaining capacity
        are offered, where ``booked`` maps a window to the orders it already holds for that day (an
        absent window counts as zero). An unserviceable request, or one whose every window is full,
        yields no delivery windows.
        """
        serviceable = self.serves(zip_code)
        if delivery_date is not None and today is not None and delivery_date < today:
            serviceable = False
        if not serviceable:
            return DarkKitchenAvailability(zip_code=zip_code, available=False, time_slots=())
        open_slots = tuple(sa.slot for sa in self.slot_availabilities(booked) if sa.is_bookable)
        return DarkKitchenAvailability(
            zip_code=zip_code,
            available=bool(open_slots),
            time_slots=open_slots,
        )

    def slot_availabilities(
        self, booked: Mapping[str, int] | None = None
    ) -> tuple[SlotAvailability, ...]:
        """Per-window capacity arithmetic for every configured slot, given the day's bookings."""
        counts = booked or {}
        return tuple(
            SlotAvailability(slot=slot, capacity=self.slot_capacity, booked=counts.get(slot, 0))
            for slot in self.time_slots
        )

    def serves(self, zip_code: str) -> bool:
        """True when ``zip_code`` falls within the configured coverage prefixes."""
        return any(prefix and zip_code.startswith(prefix) for prefix in self.served_zip_prefixes)
