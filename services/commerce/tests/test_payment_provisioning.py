"""COM-904: per-env payment provider provisioning from vault-injected secrets."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.payments.conekta import ConektaPaymentProvider
from app.payments.factory import provision_payment
from app.payments.stripe import StripePaymentProvider

# A deliberately non-real, non-key-shaped sentinel: the tests only need a distinct
# string that must never surface in a repr/str. `gitleaks:allow` keeps the secret
# scanner from flagging this fixture as a real provider credential.
SECRET = "fake-provider-secret-not-a-real-key"  # gitleaks:allow


def test_provision_payment_is_unconfigured_for_the_fake_backend() -> None:
    """COM-904: dev/CI run the fake processor, so there is nothing to provision for them."""
    assert provision_payment(Settings(payment_provider="fake")) is None


def test_provision_payment_resolves_the_real_stripe_provider_from_the_vault_secret() -> None:
    """COM-904: a real processor is provisioned from the vault-injected secret."""
    provider = provision_payment(
        Settings(
            payment_provider="stripe",
            payment_secret_key=SecretStr(SECRET),
            stripe_base_url="https://api.stripe.com",
        )
    )

    assert isinstance(provider, StripePaymentProvider)


def test_provision_payment_resolves_conekta_from_the_vault_secret() -> None:
    """COM-904: the Conekta processor is provisioned from the vault-injected secret."""
    provider = provision_payment(
        Settings(
            payment_provider="conekta",
            payment_secret_key=SecretStr(SECRET),
            conekta_base_url="https://api.conekta.io",
        )
    )

    assert isinstance(provider, ConektaPaymentProvider)


def test_provision_payment_fails_fast_on_an_unknown_processor() -> None:
    """COM-904: an unrecognized processor fails at provisioning, not at the first charge."""
    with pytest.raises(ValueError, match="Unknown COMMERCE_PAYMENT_PROVIDER"):
        provision_payment(Settings(payment_provider="paypal"))
