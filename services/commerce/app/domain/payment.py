"""Payment value objects — the provider-agnostic vocabulary of a charge (COM-201).

These small, immutable objects are the language the :class:`~app.payments.provider.PaymentProvider`
port speaks, so nothing above the port depends on Stripe's or Conekta's wire shapes. A
:class:`PaymentRequest` says *what* to charge (an amount and a provider-issued token — never raw
card data); a :class:`PaymentResult` says *what happened* (approved with a charge reference, or
declined with a reason). The concrete provider adapters translate to and from these in COM-202.

The asynchronous, cash/transfer methods speak a second pair: a :class:`PaymentVoucherRequest` asks
the provider to *issue* an offline voucher (no token to charge), and the resulting
:class:`PaymentVoucher` carries the reference the customer pays against, out of band, before it
expires — the order staying ``pending`` until a webhook confirms settlement (OXXO in COM-203, SPEI
in COM-204; confirmation in COM-206).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.money import Money


class PaymentStatus(StrEnum):
    """The outcome of a charge attempt.

    ``PENDING`` covers the asynchronous methods (OXXO voucher / SPEI transfer, COM-203/204) whose
    settlement is confirmed later by a provider webhook (COM-206).
    """

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PENDING = "pending"


@dataclass(frozen=True)
class PaymentRequest:
    """A request to charge ``amount`` against a provider-issued payment token.

    ``provider_token`` is an opaque handle the provider minted for a payment method (card, etc.) so
    **no PAN or sensitive card data ever reaches our servers** (COM-202). ``reference`` links the
    charge back to an order; ``idempotency_key`` (populated in COM-209) lets a retried request be
    de-duplicated by the provider.
    """

    amount: Money
    provider_token: str
    reference: str | None = None
    description: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class PaymentResult:
    """The outcome of a charge: an approval with a ``charge_id`` or a decline with a reason."""

    status: PaymentStatus
    provider: str
    charge_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    @property
    def is_success(self) -> bool:
        return self.status is PaymentStatus.SUCCEEDED

    @classmethod
    def succeeded(cls, *, provider: str, charge_id: str) -> PaymentResult:
        return cls(status=PaymentStatus.SUCCEEDED, provider=provider, charge_id=charge_id)

    @classmethod
    def declined(
        cls, *, provider: str, error_code: str, error_message: str | None = None
    ) -> PaymentResult:
        return cls(
            status=PaymentStatus.FAILED,
            provider=provider,
            error_code=error_code,
            error_message=error_message,
        )


@dataclass(frozen=True)
class PaymentVoucherRequest:
    """A request to issue an offline payment voucher — OXXO cash, SPEI transfer (COM-203/204).

    Unlike a card charge there is *no* provider token: the customer has nothing to charge yet. The
    provider mints a reference the customer settles later (at an OXXO store or via a bank transfer),
    so ``amount`` is what they must pay and ``reference`` links the voucher back to its order.
    ``idempotency_key`` (COM-209) lets a retried create re-issue the *same* voucher rather than a
    duplicate.
    """

    amount: Money
    reference: str | None = None
    description: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class PaymentVoucher:
    """An issued offline payment voucher awaiting asynchronous settlement (COM-203).

    The customer pays ``amount`` using ``reference`` before ``expires_at`` (``barcode_url`` points
    at a scannable barcode when the provider supplies one); the order stays ``pending`` until a
    provider webhook confirms the payment (COM-206). Its :attr:`status` is therefore always
    :attr:`PaymentStatus.PENDING` at issue.
    """

    provider: str
    reference: str
    amount: Money
    expires_at: datetime
    barcode_url: str | None = None
    status: PaymentStatus = PaymentStatus.PENDING
