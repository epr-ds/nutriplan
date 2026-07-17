"""An in-process fake payment provider for dev, CI, and tests (COM-201).

It approves every charge deterministically (minting a synthetic ``charge_id``) so the whole
payment seam can be exercised without a real processor or network — except for tokens beginning
with :data:`DECLINE_TOKEN_PREFIX`, which it declines, letting checkout/refund tests drive the
failure path too. It also records each request so a test can assert exactly what was charged.

For the asynchronous methods it likewise *issues* a voucher deterministically (COM-203): every
:meth:`create_voucher` mints an OXXO-style reference and a barcode URL, dated
:data:`VOUCHER_TTL_DAYS` ahead, and records the request in :attr:`vouchers`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.domain.payment import (
    PaymentRequest,
    PaymentResult,
    PaymentVoucher,
    PaymentVoucherRequest,
)

DECLINE_TOKEN_PREFIX = "tok_decline"
VOUCHER_TTL_DAYS = 3


class FakePaymentProvider:
    """Deterministically approves charges (declining ``tok_decline*``); records what it charged."""

    name = "fake"

    def __init__(self) -> None:
        self.charges: list[PaymentRequest] = []
        self.vouchers: list[PaymentVoucherRequest] = []

    def charge(self, request: PaymentRequest) -> PaymentResult:
        self.charges.append(request)
        if request.provider_token.startswith(DECLINE_TOKEN_PREFIX):
            return PaymentResult.declined(
                provider=self.name,
                error_code="card_declined",
                error_message="The fake provider declined this token.",
            )
        return PaymentResult.succeeded(provider=self.name, charge_id=f"fake_ch_{uuid.uuid4().hex}")

    def create_voucher(self, request: PaymentVoucherRequest) -> PaymentVoucher:
        self.vouchers.append(request)
        reference = f"oxxo_{uuid.uuid4().hex[:12]}"
        return PaymentVoucher(
            provider=self.name,
            reference=reference,
            amount=request.amount,
            expires_at=datetime.now(UTC) + timedelta(days=VOUCHER_TTL_DAYS),
            barcode_url=f"https://vouchers.example/{reference}.png",
        )
