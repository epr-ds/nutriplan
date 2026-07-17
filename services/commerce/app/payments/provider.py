"""The payment provider port (COM-201).

The application layer depends only on this small surface: hand it a :class:`PaymentRequest` and it
charges through some provider, returning a :class:`PaymentResult`. Keeping it a port lets Stripe and
Conekta be interchangeable adapters (an in-process fake backs dev/CI and tests), so nothing above
this seam imports a payment SDK or assumes a specific processor.

The asynchronous cash/transfer methods add a second operation: :meth:`create_voucher` asks the
provider to *issue* an offline voucher (OXXO in COM-203, SPEI in COM-204) the customer settles out
of band, leaving the order ``pending`` until a webhook confirms it (COM-206).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.payment import (
    PaymentRequest,
    PaymentResult,
    PaymentVoucher,
    PaymentVoucherRequest,
)


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

    def create_voucher(self, request: PaymentVoucherRequest) -> PaymentVoucher:
        """Issue an offline voucher (OXXO/SPEI) for ``request.amount`` to be settled later."""
        ...
