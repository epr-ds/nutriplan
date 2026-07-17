"""The Stripe :class:`~app.payments.provider.PaymentProvider` adapter (COM-201).

COM-201 establishes the adapter and its configuration: it captures the Stripe secret key and API
base URL and takes its place behind the port so the provider is selectable by config. The secret is
held privately and kept out of ``repr``/logs. The concrete charge call against Stripe's API is
implemented in COM-202 (card tokenization & charge), which depends on this story.
"""

from __future__ import annotations

from app.domain.payment import (
    PaymentRequest,
    PaymentResult,
    PaymentTransfer,
    PaymentTransferRequest,
    PaymentVoucher,
    PaymentVoucherRequest,
    PaymentWebhookEvent,
)


class StripePaymentProvider:
    """Charges via Stripe. Configured here (COM-201); ``charge`` is wired to the API in COM-202."""

    name = "stripe"

    def __init__(self, secret_key: str, *, base_url: str = "https://api.stripe.com") -> None:
        self._secret_key = secret_key
        self._base_url = base_url

    @property
    def base_url(self) -> str:
        return self._base_url

    def charge(self, request: PaymentRequest) -> PaymentResult:
        raise NotImplementedError("Live Stripe charging is implemented in COM-202.")

    def create_voucher(self, request: PaymentVoucherRequest) -> PaymentVoucher:
        raise NotImplementedError("Live Stripe OXXO voucher issuance is implemented in COM-203.")

    def create_transfer(self, request: PaymentTransferRequest) -> PaymentTransfer:
        raise NotImplementedError("Live Stripe SPEI transfer issuance is implemented in COM-204.")

    def parse_webhook(self, payload: bytes, signature: str) -> PaymentWebhookEvent:
        raise NotImplementedError("Live Stripe webhook verification is implemented in COM-206.")

    def __repr__(self) -> str:
        # The secret key is deliberately excluded so it never leaks into logs or tracebacks.
        return f"StripePaymentProvider(base_url={self._base_url!r})"
