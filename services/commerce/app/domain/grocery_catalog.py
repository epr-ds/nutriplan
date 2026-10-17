"""Provider-agnostic grocery vocabulary the anti-corruption layer speaks (COM-402).

These immutable value objects are the *only* types allowed to cross the grocery-provider ACL
(:class:`~app.grocery.adapter.GroceryProviderAdapter`). Each provider adapter translates its own
wire shapes to and from these, so nothing above the port ever sees a FreshBasket / Walmart /
Chedraui payload:

* **search** speaks :class:`GrocerySearchQuery` -> :class:`GrocerySearchResult` of
  :class:`GroceryProduct` (prices normalised to :class:`~app.domain.money.Money`);
* **ordering** speaks :class:`GroceryOrderRequest` -> :class:`GroceryOrderPlacement`;
* **status** is the canonical :class:`GroceryOrderStatus` a provider's own status strings are
  mapped onto -- an unrecognised value maps to ``UNKNOWN`` rather than leaking the raw string.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.domain.money import Money


@dataclass(frozen=True)
class GrocerySearchItem:
    """One requested ingredient line in a search (mirrors the contract's ``items[]``)."""

    ingredient: str
    quantity: Decimal | None = None
    unit: str | None = None


@dataclass(frozen=True)
class GrocerySearchQuery:
    """A provider-agnostic product search: what to find and where to deliver it.

    ``providers`` optionally narrows the fan-out to specific provider ids; empty means every
    enabled provider. ``zip_code`` scopes the search to a delivery area.
    """

    zip_code: str
    items: tuple[GrocerySearchItem, ...] = ()
    providers: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroceryProduct:
    """A single product a provider can offer for a search (one search hit).

    ``provider_id`` ties the hit back to the :class:`~app.domain.grocery.GroceryProvider` that can
    fulfil it and ``sku`` is that provider's stable product id (later an order line references it).
    ``price`` is normalised :class:`~app.domain.money.Money`; ``matched_ingredient`` records which
    requested item this hit answered, when known.
    """

    provider_id: str
    sku: str
    name: str
    price: Money
    unit: str | None = None
    in_stock: bool = True
    matched_ingredient: str | None = None


@dataclass(frozen=True)
class GrocerySearchResult:
    """One provider's answer to a search: the products it offers, in provider order."""

    provider_id: str
    products: tuple[GroceryProduct, ...] = ()


class GroceryOrderStatus(StrEnum):
    """The canonical, provider-agnostic lifecycle of a grocery order (COM-402).

    Every provider reports fulfilment progress in its own words; the ACL maps those onto this fixed
    set so the rest of the platform reasons about one lifecycle. ``UNKNOWN`` is the safe default for
    a status an adapter does not recognise -- the raw provider string never escapes the seam.
    """

    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class GroceryOrderLine:
    """A single line to purchase from a provider: a provider ``sku`` and a unit ``quantity``."""

    sku: str
    quantity: int


@dataclass(frozen=True)
class GroceryOrderRequest:
    """A provider-agnostic request to place a grocery order with one provider.

    ``reference`` carries our own order id through the seam so a later status poll or provider
    webhook can be tied back to the originating order (COM-408).
    """

    provider_id: str
    reference: str
    zip_code: str
    lines: tuple[GroceryOrderLine, ...] = ()


@dataclass(frozen=True)
class GroceryOrderPlacement:
    """The outcome of placing an order with a provider (COM-402).

    Carries the provider's own ``external_order_id`` (what a status poll uses) and the canonical
    :class:`GroceryOrderStatus` the placement settled at -- ``PENDING`` until the provider accepts.
    """

    provider_id: str
    external_order_id: str
    status: GroceryOrderStatus = GroceryOrderStatus.PENDING
    total: Money | None = None
