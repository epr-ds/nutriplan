"""COM-301 use case: check whether a dark kitchen serves a delivery area.

A thin read-side application service over the
:class:`~app.domain.fulfillment.DarkKitchenServiceArea`
policy. It owns the notion of "now" so the pure domain policy stays clock-free and deterministic:
the service resolves ``today`` via an injected clock (defaulting to :func:`datetime.date.today`) and
passes it into the policy, which uses it to reject already-past delivery dates. Tests inject a fixed
clock for reproducibility.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from app.application.queries import DarkKitchenAvailabilityQuery
from app.domain.fulfillment import DarkKitchenAvailability, DarkKitchenServiceArea


class CheckDarkKitchenAvailabilityService:
    """Answers dark-kitchen availability for a postcode/date (COM-301)."""

    def __init__(
        self,
        service_area: DarkKitchenServiceArea,
        *,
        clock: Callable[[], date] = date.today,
    ) -> None:
        self._service_area = service_area
        self._clock = clock

    def check(self, query: DarkKitchenAvailabilityQuery) -> DarkKitchenAvailability:
        return self._service_area.check(
            query.zip_code,
            delivery_date=query.delivery_date,
            today=self._clock(),
        )
