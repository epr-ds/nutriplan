"""The ``SavedPaymentMethod`` entity — a tokenized payment method a user has stored (COM-207).

A saved method is a **reference only**: it holds the durable token the payment provider minted for
the instrument plus non-sensitive display metadata (brand, last four, expiry) so the app can show
"Visa ****4242" at checkout. A PAN, CVV or any sensitive card datum is **never** stored or even
accepted — on-device tokenization yields the token before it ever reaches us, so only the token
crosses our boundary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.enums import PaymentMethodType
from app.domain.errors import PaymentMethodValidationError


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class SavedPaymentMethod:
    """A user's stored, tokenized payment method (a card or wallet), owner-scoped by ``user_id``.

    ``token`` is the provider's durable handle for the instrument — the only thing that lets a later
    charge reuse it — and is treated as a stored credential: it is persisted but **never** projected
    back onto the API. ``brand``/``last4``/``exp_month``/``exp_year`` are the non-sensitive display
    metadata (present for cards, absent for wallets like PayPal). Instances are immutable: a saved
    method is added or deleted, never edited in place.
    """

    user_id: uuid.UUID
    type: PaymentMethodType
    token: str
    brand: str | None = None
    last4: str | None = None
    exp_month: int | None = None
    exp_year: int | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.token or not self.token.strip():
            raise PaymentMethodValidationError("a payment-method token is required")
        if self.last4 is not None and (len(self.last4) != 4 or not self.last4.isdigit()):
            raise PaymentMethodValidationError("last4 must be exactly four digits")
        if self.exp_month is not None and not 1 <= self.exp_month <= 12:
            raise PaymentMethodValidationError("exp_month must be between 1 and 12")
        if self.exp_year is not None and self.exp_year < 2000:
            raise PaymentMethodValidationError("exp_year must be a four-digit calendar year")
