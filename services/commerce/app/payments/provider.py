"""The payment provider port (COM-201).

The application layer depends only on this small surface: hand it a :class:`PaymentRequest` and it
charges through some provider, returning a :class:`PaymentResult`. Keeping it a port lets Stripe and
Conekta be interchangeable adapters (an in-process fake backs dev/CI and tests), so nothing above
this seam imports a payment SDK or assumes a specific processor.

The asynchronous cash/transfer methods add two more operations: :meth:`create_voucher` asks the
provider to *issue* an offline cash voucher (OXXO, COM-203) and :meth:`create_transfer` asks for
bank-transfer instructions (SPEI, COM-204), both settled out of band and leaving the order
``pending`` until a webhook confirms it (COM-206). :meth:`parse_webhook` closes that loop: it
verifies an inbound provider webhook's signature and normalises it into a
:class:`~app.domain.payment.PaymentWebhookEvent` the application can act on.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.payment import (
    PaymentRequest,
    PaymentResult,
    PaymentTransfer,
    PaymentTransferRequest,
    PaymentVoucher,
    PaymentVoucherRequest,
    PaymentWebhookEvent,
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
        """Issue an offline cash voucher (OXXO) for ``request.amount`` to be settled later."""
        ...

    def create_transfer(self, request: PaymentTransferRequest) -> PaymentTransfer:
        """Issue bank-transfer instructions (SPEI) for ``request.amount`` to be settled later."""
        ...

    def parse_webhook(self, payload: bytes, signature: str) -> PaymentWebhookEvent:
        """Verify a webhook's ``signature`` over the raw ``payload`` and parse it (COM-206).

        Raises :class:`~app.domain.errors.WebhookVerificationError` when the signature does not
        match or the verified body cannot be understood.
        """
        ...
