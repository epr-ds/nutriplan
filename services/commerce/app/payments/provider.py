"""The payment provider port (COM-201).

The application layer depends only on this small surface: hand it a :class:`PaymentRequest` and it
charges through some provider, returning a :class:`PaymentResult`. Keeping it a port lets Stripe and
Conekta be interchangeable adapters (an in-process fake backs dev/CI and tests), so nothing above
this seam imports a payment SDK or assumes a specific processor.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.payment import PaymentRequest, PaymentResult


@runtime_checkable
class PaymentProvider(Protocol):
    """Charges a payment against a provider, provider-agnostically."""

    @property
    def name(self) -> str:
        """A stable identifier for the backing provider (e.g. ``"stripe"``)."""
        ...

    def charge(self, request: PaymentRequest) -> PaymentResult:
        """Charge ``request.amount`` against ``request.provider_token`` and report the outcome."""
        ...
