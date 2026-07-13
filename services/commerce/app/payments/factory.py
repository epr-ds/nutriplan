"""Choose the payment provider backend from configuration (COM-201).

``COMMERCE_PAYMENT_PROVIDER`` selects the processor (``stripe`` / ``conekta`` / ``fake``); the real
providers are constructed with the secret pulled from ``COMMERCE_PAYMENT_SECRET_KEY`` (injected from
the vault in production, COM-904) and the provider's API base URL. Leave the provider unset (or
``fake``) and an in-process fake is used, which is correct for dev/CI and tests. The choice is
invisible above the port.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.payments.conekta import ConektaPaymentProvider
from app.payments.fake import FakePaymentProvider
from app.payments.provider import PaymentProvider
from app.payments.stripe import StripePaymentProvider


def build_payment_provider(settings: Settings | None = None) -> PaymentProvider:
    """Return the configured payment provider, defaulting to the in-process fake.

    Raises :class:`ValueError` for an unrecognized ``COMMERCE_PAYMENT_PROVIDER`` so a
    misconfiguration fails fast at startup rather than at the first charge.
    """
    settings = settings or default_settings
    choice = settings.payment_provider.strip().lower()
    secret = settings.payment_secret_key.get_secret_value()
    if choice == "stripe":
        return StripePaymentProvider(secret, base_url=settings.stripe_base_url)
    if choice == "conekta":
        return ConektaPaymentProvider(secret, base_url=settings.conekta_base_url)
    if choice in ("", "fake"):
        return FakePaymentProvider()
    raise ValueError(
        f"Unknown COMMERCE_PAYMENT_PROVIDER {choice!r}; expected 'stripe', 'conekta', or 'fake'"
    )
