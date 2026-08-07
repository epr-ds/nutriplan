"""Dark-kitchen fulfillment domain (COM-301).

A dark kitchen delivers prepared orders within a service area. This module models, as pure domain
logic, whether that area covers a given delivery postcode and which delivery windows it offers:

* :class:`DarkKitchenServiceArea` is the coverage + schedule policy — a zip is served when its
  postcode begins with one of the configured prefixes, and every serviceable day offers the same
  fixed set of delivery windows. Per-day capacity and slot exhaustion are **not** modelled here;
  that arrives with the capacity/time-slot model in COM-302 and slot reservation in COM-304.
* :class:`DarkKitchenAvailability` is the immutable result the API projects onto
  ``AvailabilityResponse``.

Keeping this in the domain (rather than the router) means the availability rules are unit-testable
without HTTP and can grow into the richer COM-302 model without touching the transport layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DarkKitchenAvailability:
    """Whether a dark kitchen serves a delivery area, and the windows it can deliver in.

    ``time_slots`` is empty whenever ``available`` is ``False`` — an area that is not served offers
    no windows — so callers never have to reconcile the two fields.
    """

    zip_code: str
    available: bool
    time_slots: tuple[str, ...] = ()


@dataclass(frozen=True)
class DarkKitchenServiceArea:
    """Coverage and daily delivery schedule for dark-kitchen fulfillment (COM-301).

    Coverage is by Mexican postal-code (*código postal*) prefix: a postcode is served when it starts
    with any configured prefix, so a whole delegation/municipality can be covered by its leading
    digits. ``time_slots`` are the delivery windows offered on every serviceable day (the per-day
    capacity model is COM-302); they are surfaced only for a serviceable request.
    """

    served_zip_prefixes: tuple[str, ...]
    time_slots: tuple[str, ...]

    def check(
        self,
        zip_code: str,
        *,
        delivery_date: date | None = None,
        today: date | None = None,
    ) -> DarkKitchenAvailability:
        """Decide availability for ``zip_code`` (optionally for a specific ``delivery_date``).

        The area must cover the postcode; additionally, when both a ``delivery_date`` and a
        ``today`` reference are given, a date already in the past is not serviceable (a kitchen
        cannot deliver in the past). An unserviceable request yields no delivery windows.
        """
        serviceable = self.serves(zip_code)
        if delivery_date is not None and today is not None and delivery_date < today:
            serviceable = False
        return DarkKitchenAvailability(
            zip_code=zip_code,
            available=serviceable,
            time_slots=self.time_slots if serviceable else (),
        )

    def serves(self, zip_code: str) -> bool:
        """True when ``zip_code`` falls within the configured coverage prefixes."""
        return any(prefix and zip_code.startswith(prefix) for prefix in self.served_zip_prefixes)
