"""Fulfillment API router (COM-301 dark-kitchen availability, COM-401 grocery providers)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import (
    CurrentPrincipal,
    DarkKitchenAvailabilityServiceDep,
    GroceryProvidersServiceDep,
)
from app.api.schemas import AvailabilityResponse, ProviderResponse
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


@router.get(
    "/fulfillment/grocery/providers",
    response_model=list[ProviderResponse],
    summary="List available grocery providers",
)
def list_grocery_providers(
    principal: CurrentPrincipal,
    service: GroceryProvidersServiceDep,
) -> list[ProviderResponse]:
    """List the grocery delivery providers enabled in this environment (COM-401).

    Returns the configured providers that are enabled for the current environment, in configured
    order; a disabled provider is omitted rather than returned with a flag. The listing is not
    caller-specific, but a valid bearer token is still required (else ``401``).
    """
    providers = service.list_available()
    return [ProviderResponse.from_domain(provider) for provider in providers]
