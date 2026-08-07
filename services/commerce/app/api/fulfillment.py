"""Fulfillment API router (COM-301 dark-kitchen availability)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentPrincipal, DarkKitchenAvailabilityServiceDep
from app.api.schemas import AvailabilityResponse
from app.application.queries import DarkKitchenAvailabilityQuery

router = APIRouter(tags=["Fulfillment"])


@router.get(
    "/fulfillment/dark-kitchen/availability",
    response_model=AvailabilityResponse,
    summary="Check dark-kitchen availability",
)
def get_dark_kitchen_availability(
    principal: CurrentPrincipal,
    service: DarkKitchenAvailabilityServiceDep,
    zip_code: Annotated[str, Query(alias="zipCode", pattern=r"^\d{5}$")],
    delivery_date: Annotated[date | None, Query(alias="deliveryDate")] = None,
) -> AvailabilityResponse:
    """Report whether a dark kitchen serves ``zipCode`` and, if so, the windows it delivers in.

    Availability is coverage-based (COM-301): a served postcode returns ``available: true`` with the
    kitchen's daily delivery windows; an out-of-area postcode returns ``available: false`` and no
    windows. An optional ``deliveryDate`` already in the past is likewise not serviceable. The
    ``zipCode`` must be a 5-digit Mexican postal code (else ``422``), and a valid bearer token is
    required (else ``401``).
    """
    availability = service.check(
        DarkKitchenAvailabilityQuery(zip_code=zip_code, delivery_date=delivery_date)
    )
    return AvailabilityResponse.from_domain(availability)
