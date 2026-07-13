"""An in-process fake payment provider for dev, CI, and tests (COM-201).

It approves every charge deterministically (minting a synthetic ``charge_id``) so the whole
payment seam can be exercised without a real processor or network — except for tokens beginning
with :data:`DECLINE_TOKEN_PREFIX`, which it declines, letting checkout/refund tests drive the
failure path too. It also records each request so a test can assert exactly what was charged.
"""

from __future__ import annotations

import uuid

from app.domain.payment import PaymentRequest, PaymentResult

DECLINE_TOKEN_PREFIX = "tok_decline"


class FakePaymentProvider:
    """Deterministically approves charges (declining ``tok_decline*``); records what it charged."""

    name = "fake"

    def __init__(self) -> None:
        self.charges: list[PaymentRequest] = []

    def charge(self, request: PaymentRequest) -> PaymentResult:
        self.charges.append(request)
        if request.provider_token.startswith(DECLINE_TOKEN_PREFIX):
            return PaymentResult.declined(
                provider=self.name,
                error_code="card_declined",
                error_message="The fake provider declined this token.",
            )
        return PaymentResult.succeeded(provider=self.name, charge_id=f"fake_ch_{uuid.uuid4().hex}")
