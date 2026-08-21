"""Grocery-provider fulfillment domain (COM-401).

The read-side catalogue of grocery delivery providers the service can fulfil through. Modelled, as
pure domain logic, as an immutable registry of providers with a per-provider ``enabled`` flag:

* :class:`GroceryProvider` is one configured provider — its stable ``id`` (used later as an order's
  ``providerId`` and to route search/placement in COM-403/408), display ``name``, optional ``logo``
  and human ``estimated_delivery`` blurb, and whether it is ``enabled`` in this environment.
* :class:`GroceryProviderRegistry` is the enable/disable policy: :meth:`available` returns only the
  enabled providers, in configured order, so a provider can be dark-launched (present in config but
  disabled) or turned off per environment without a code change.

Which providers exist, and which are enabled, is configuration (wired in ``deps`` from settings);
the domain only decides *what "available" means*, so the rule stays unit-testable without HTTP or
config.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import ProviderType


@dataclass(frozen=True)
class GroceryProvider:
    """A single configured grocery delivery provider (COM-401).

    ``id`` is the stable machine identifier (e.g. ``freshbasket``) referenced by
    ``grocery_delivery`` orders and grocery search/placement; the remaining fields are display
    metadata. ``enabled`` gates whether the provider is offered in the current environment.
    """

    id: str
    name: str
    enabled: bool = True
    logo_url: str | None = None
    estimated_delivery: str | None = None
    type: ProviderType = ProviderType.GROCERY


@dataclass(frozen=True)
class GroceryProviderRegistry:
    """The configured grocery providers and the per-environment enable/disable policy (COM-401).

    Holds the full catalogue in configured order; :meth:`available` projects it to just the enabled
    providers, so callers only ever see providers they may actually use while a disabled provider
    stays defined (and easy to re-enable) rather than deleted.
    """

    providers: tuple[GroceryProvider, ...] = ()

    def available(self) -> tuple[GroceryProvider, ...]:
        """The enabled providers, in configured order."""
        return tuple(provider for provider in self.providers if provider.enabled)
