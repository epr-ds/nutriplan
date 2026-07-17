"""The Conekta :class:`~app.payments.provider.PaymentProvider` adapter (COM-201).

Conekta is the Mexico-focused processor; this adapter mirrors the Stripe one so either is selectable
by configuration. COM-201 wires up the adapter and its credentials (secret held privately, kept out
of ``repr``/logs); the concrete charge call against Conekta's API lands in COM-202.
"""

from __future__ import annotations

from app.domain.payment import (
    PaymentRequest,
    PaymentResult,
    PaymentVoucher,
    PaymentVoucherRequest,
)


class ConektaPaymentProvider:
    """Charges via Conekta. Configured here (COM-201); ``charge`` is wired to the API in COM-202."""

    name = "conekta"

    def __init__(self, secret_key: str, *, base_url: str = "https://api.conekta.io") -> None:
        self._secret_key = secret_key
        self._base_url = base_url

    @property
    def base_url(self) -> str:
        return self._base_url

    def charge(self, request: PaymentRequest) -> PaymentResult:
        raise NotImplementedError("Live Conekta charging is implemented in COM-202.")

    def create_voucher(self, request: PaymentVoucherRequest) -> PaymentVoucher:
        raise NotImplementedError("Live Conekta OXXO voucher issuance is implemented in COM-203.")

    def __repr__(self) -> str:
        # The secret key is deliberately excluded so it never leaks into logs or tracebacks.
        return f"ConektaPaymentProvider(base_url={self._base_url!r})"
