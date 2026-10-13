"""An in-process fake payment provider for dev, CI, and tests (COM-201).

It approves every charge deterministically (minting a synthetic ``charge_id``) so the whole
payment seam can be exercised without a real processor or network — except for tokens beginning
with :data:`DECLINE_TOKEN_PREFIX`, which it declines, letting checkout/refund tests drive the
failure path too. It also records each request so a test can assert exactly what was charged.

For the asynchronous methods it likewise *issues* the instrument deterministically: every
:meth:`create_voucher` mints an OXXO-style reference and a barcode URL (COM-203), every
:meth:`create_transfer` mints an 18-digit SPEI CLABE and reference (COM-204), and every
:meth:`create_approval` mints a PayPal-style order reference and an ``approval_url`` (COM-205), all
dated ahead and recorded (in :attr:`vouchers` / :attr:`transfers` / :attr:`approvals`).

:meth:`parse_webhook` closes the async loop (COM-206): it verifies an HMAC-SHA256 signature over
the raw request body using the configured ``webhook_secret`` (constant-time) and normalises the
JSON event into a :class:`PaymentWebhookEvent`, exactly as a real provider adapter would. Finally
:meth:`refund` returns all or part of a captured charge deterministically (minting a synthetic
``refund_id`` and recording the request in :attr:`refunds`) so the cancel-refund path (COM-208) is
exercisable without a real processor.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

from app.domain.errors import WebhookVerificationError
from app.domain.payment import (
    PaymentApproval,
    PaymentApprovalRequest,
    PaymentEventType,
    PaymentRefund,
    PaymentRefundRequest,
    PaymentRequest,
    PaymentResult,
    PaymentTransfer,
    PaymentTransferRequest,
    PaymentVoucher,
    PaymentVoucherRequest,
    PaymentWebhookEvent,
)

DECLINE_TOKEN_PREFIX = "tok_decline"
VOUCHER_TTL_DAYS = 3
# A redirect approval (PayPal) expires far sooner than a cash voucher / transfer -- the customer is
# meant to approve it in-session, so the fake mints a short, realistic window (COM-205).
APPROVAL_TTL_HOURS = 3


class FakePaymentProvider:
    """Deterministically approves charges (declining ``tok_decline*``); records what it charged."""

    name = "fake"

    def __init__(self, webhook_secret: str = "") -> None:
        self._webhook_secret = webhook_secret
        self.charges: list[PaymentRequest] = []
        self.vouchers: list[PaymentVoucherRequest] = []
        self.transfers: list[PaymentTransferRequest] = []
        self.approvals: list[PaymentApprovalRequest] = []
        self.refunds: list[PaymentRefundRequest] = []

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

    def create_transfer(self, request: PaymentTransferRequest) -> PaymentTransfer:
        self.transfers.append(request)
        return PaymentTransfer(
            provider=self.name,
            clabe=f"{uuid.uuid4().int % 10**18:018d}",
            reference=f"spei_{uuid.uuid4().hex[:12]}",
            amount=request.amount,
            expires_at=datetime.now(UTC) + timedelta(days=VOUCHER_TTL_DAYS),
        )

    def create_approval(self, request: PaymentApprovalRequest) -> PaymentApproval:
        self.approvals.append(request)
        reference = f"paypal_{uuid.uuid4().hex[:12]}"
        return PaymentApproval(
            provider=self.name,
            reference=reference,
            approval_url=f"https://paypal.example/checkout/{reference}",
            amount=request.amount,
            expires_at=datetime.now(UTC) + timedelta(hours=APPROVAL_TTL_HOURS),
        )

    def refund(self, request: PaymentRefundRequest) -> PaymentRefund:
        self.refunds.append(request)
        return PaymentRefund(
            provider=self.name,
            refund_id=f"fake_re_{uuid.uuid4().hex}",
            amount=request.amount,
        )

    def parse_webhook(self, payload: bytes, signature: str) -> PaymentWebhookEvent:
        expected = hmac.new(
            self._webhook_secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature or ""):
            raise WebhookVerificationError("payment webhook signature does not match")
        try:
            body = json.loads(payload)
            event_type = PaymentEventType(body["type"])
            data = body["data"]
            reference = data["reference"]
            charge_id = data.get("charge_id")
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise WebhookVerificationError("payment webhook payload is malformed") from exc
        if not isinstance(reference, str) or not reference:
            raise WebhookVerificationError("payment webhook is missing a reference")
        return PaymentWebhookEvent(
            type=event_type,
            reference=reference,
            provider=self.name,
            charge_id=charge_id if isinstance(charge_id, str) else None,
        )
