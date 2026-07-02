"""``Money`` value object — an immutable (amount, currency) pair for order pricing.

Amounts are quantized to two decimal places (MXN minor units). Arithmetic is currency-safe:
adding or comparing across currencies raises rather than silently coercing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_CENTS = Decimal("0.01")


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "MXN"

    def __post_init__(self) -> None:
        amount = self.amount if isinstance(self.amount, Decimal) else Decimal(str(self.amount))
        object.__setattr__(self, "amount", amount.quantize(_CENTS, rounding=ROUND_HALF_UP))
        if not self.currency:
            raise ValueError("Money requires a currency")

    @classmethod
    def zero(cls, currency: str = "MXN") -> Money:
        return cls(Decimal("0"), currency)

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} != {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __mul__(self, factor: Decimal | int | float) -> Money:
        return Money(self.amount * Decimal(str(factor)), self.currency)

    @property
    def formatted(self) -> str:
        """Human-readable amount, e.g. ``$1,234.50 MXN``."""
        return f"${self.amount:,.2f} {self.currency}"
