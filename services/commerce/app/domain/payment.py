"""Payment value objects — the provider-agnostic vocabulary of a charge (COM-201).

These small, immutable objects are the language the :class:`~app.payments.provider.PaymentProvider`
port speaks, so nothing above the port depends on Stripe's or Conekta's wire shapes. A
:class:`PaymentRequest` says *what* to charge (an amount and a provider-issued token — never raw
card data); a :class:`PaymentResult` says *what happened* (approved with a charge reference, or
declined with a reason). The concrete provider adapters translate to and from these in COM-202.

The asynchronous methods speak their own pairs. A :class:`PaymentVoucherRequest` asks the provider
to *issue* an offline cash voucher (no token to charge) and the resulting :class:`PaymentVoucher`
carries the reference the customer pays against at a store before it expires (OXXO, COM-203). A
:class:`PaymentTransferRequest` likewise asks for bank-transfer instructions and the resulting
:class:`PaymentTransfer` carries the destination ``clabe`` and reference the customer transfers to
(SPEI, COM-204). Either way the order stays ``pending`` until a webhook confirms settlement
(COM-206).

That settlement arrives as a :class:`PaymentWebhookEvent`: the provider posts a signed event whose
:class:`PaymentEventType` tells us the async payment succeeded or failed, carrying the ``reference``
that links it back to the order so the handler can confirm or fail it (COM-206).
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


class PaymentEventType(StrEnum):
    """The kind of asynchronous settlement a provider webhook reports (COM-206).

    The provider posts one of these once an OXXO voucher / SPEI transfer settles out of band:
    ``CONFIRMED`` means the funds arrived (confirm the order), ``FAILED`` means they did not (fail
    it). The concrete provider adapters map their own event names onto this canonical pair.
    """

    CONFIRMED = "payment.confirmed"
    FAILED = "payment.failed"


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
    """A request to issue an offline cash voucher — OXXO (COM-203).

    Unlike a card charge there is *no* provider token: the customer has nothing to charge yet. The
    provider mints a reference the customer settles later at a store, so ``amount`` is what they
    must pay and ``reference`` links the voucher back to its order. ``idempotency_key`` (COM-209)
    lets a retried create re-issue the *same* voucher rather than a duplicate.
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


@dataclass(frozen=True)
class PaymentTransferRequest:
    """A request to issue bank-transfer instructions — SPEI (COM-204).

    Like a voucher there is *no* provider token: the customer pushes the funds themselves. The
    provider mints a destination ``clabe`` and reference the customer transfers to, so ``amount`` is
    what they must send and ``reference`` links the transfer back to its order. ``idempotency_key``
    (COM-209) lets a retried create re-issue the *same* instructions rather than a duplicate.
    """

    amount: Money
    reference: str | None = None
    description: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class PaymentTransfer:
    """Issued bank-transfer instructions awaiting asynchronous settlement (SPEI, COM-204).

    The customer transfers ``amount`` to the interbank ``clabe`` quoting ``reference`` before
    ``expires_at``; the order stays ``pending`` until a provider webhook confirms the transfer
    landed (COM-206). Its :attr:`status` is therefore always :attr:`PaymentStatus.PENDING` at issue.
    """

    provider: str
    clabe: str
    reference: str
    amount: Money
    expires_at: datetime
    status: PaymentStatus = PaymentStatus.PENDING


@dataclass(frozen=True)
class PaymentWebhookEvent:
    """A verified provider webhook reporting an async payment's settlement (COM-206).

    The provider posts this once an OXXO voucher / SPEI transfer settles out of band; the adapter
    verifies its signature and normalises it into this canonical shape. ``reference`` is the value
    we handed the provider at issue (the order id), so the handler can find the order and either
    confirm it (:attr:`PaymentEventType.CONFIRMED`) or fail it (:attr:`PaymentEventType.FAILED`).
    ``charge_id`` is the provider's settlement reference when supplied (kept so a later refund in
    COM-208 has something to act on).
    """

    type: PaymentEventType
    reference: str
    provider: str
    charge_id: str | None = None
