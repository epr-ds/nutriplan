"""Payment value objects — the provider-agnostic vocabulary of a charge (COM-201).

These small, immutable objects are the language the :class:`~app.payments.provider.PaymentProvider`
port speaks, so nothing above the port depends on Stripe's or Conekta's wire shapes. A
:class:`PaymentRequest` says *what* to charge (an amount and a provider-issued token — never raw
card data); a :class:`PaymentResult` says *what happened* (approved with a charge reference, or
declined with a reason). The concrete provider adapters translate to and from these in COM-202.
"""

from __future__ import annotations

from dataclasses import dataclass
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
