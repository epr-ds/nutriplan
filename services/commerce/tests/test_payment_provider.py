"""COM-201: the payment provider abstraction, its adapters, config selection, and secret safety.

No live processor and no network. Proves the port's vocabulary (`PaymentResult` helpers), the
in-process fake (approves, records, and declines a sentinel token), that the real Stripe/Conekta
adapters are configured but defer the actual charge to COM-202, that the secret key is never exposed
in a repr/str (AC "keys never logged"), and that the factory selects the backend from config.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.domain.money import Money
from app.domain.payment import PaymentRequest, PaymentResult, PaymentStatus
from app.payments.conekta import ConektaPaymentProvider
from app.payments.factory import build_payment_provider
from app.payments.fake import DECLINE_TOKEN_PREFIX, FakePaymentProvider
from app.payments.provider import PaymentProvider
from app.payments.stripe import StripePaymentProvider

# A deliberately non-real, non-key-shaped sentinel: the tests only need a distinct
# string that must never surface in a repr/str. `gitleaks:allow` keeps the secret
# scanner from flagging this fixture as a real provider credential.
SECRET = "fake-provider-secret-not-a-real-key"  # gitleaks:allow


def _request(*, token: str = "tok_visa", amount: str = "250.00") -> PaymentRequest:
    return PaymentRequest(amount=Money(Decimal(amount)), provider_token=token, reference="order-1")


# --------------------------------------------------------------------------- domain vocabulary


def test_payment_result_success_helper():
    result = PaymentResult.succeeded(provider="stripe", charge_id="ch_1")

    assert result.is_success
    assert result.status is PaymentStatus.SUCCEEDED
    assert result.charge_id == "ch_1"
    assert result.error_code is None


def test_payment_result_decline_helper():
    result = PaymentResult.declined(
        provider="stripe", error_code="card_declined", error_message="nope"
    )

    assert not result.is_success
    assert result.status is PaymentStatus.FAILED
    assert result.error_code == "card_declined"
    assert result.charge_id is None


# --------------------------------------------------------------------------- fake provider


def test_fake_provider_approves_and_records_the_charge():
    provider = FakePaymentProvider()
    request = _request(token="tok_visa")

    result = provider.charge(request)

    assert result.is_success
    assert result.provider == "fake"
    assert result.charge_id is not None
    assert result.charge_id.startswith("fake_ch_")
    assert provider.charges == [request]


def test_fake_provider_declines_a_decline_token():
    provider = FakePaymentProvider()

    result = provider.charge(_request(token=f"{DECLINE_TOKEN_PREFIX}_visa"))

    assert not result.is_success
    assert result.status is PaymentStatus.FAILED
    assert result.error_code == "card_declined"
    assert result.charge_id is None


# --------------------------------------------------------------------------- real adapters


@pytest.mark.parametrize(
    ("provider_cls", "expected_name"),
    [(StripePaymentProvider, "stripe"), (ConektaPaymentProvider, "conekta")],
)
def test_real_adapters_are_named_and_configured(provider_cls, expected_name):
    provider = provider_cls(SECRET, base_url="https://api.example.test")

    assert provider.name == expected_name
    assert provider.base_url == "https://api.example.test"


@pytest.mark.parametrize("provider_cls", [StripePaymentProvider, ConektaPaymentProvider])
def test_real_adapters_defer_charge_to_com202(provider_cls):
    provider = provider_cls(SECRET, base_url="https://api.example.test")

    with pytest.raises(NotImplementedError, match="COM-202"):
        provider.charge(_request())


@pytest.mark.parametrize("provider_cls", [StripePaymentProvider, ConektaPaymentProvider])
def test_real_adapters_never_expose_the_secret_key(provider_cls):
    provider = provider_cls(SECRET, base_url="https://api.example.test")

    assert SECRET not in repr(provider)
    assert SECRET not in str(provider)


@pytest.mark.parametrize(
    "provider",
    [
        FakePaymentProvider(),
        StripePaymentProvider(SECRET, base_url="https://s.test"),
        ConektaPaymentProvider(SECRET, base_url="https://c.test"),
    ],
)
def test_adapters_satisfy_the_payment_provider_protocol(provider):
    assert isinstance(provider, PaymentProvider)
    assert isinstance(provider.name, str)


# --------------------------------------------------------------------------- secret never logged


def test_settings_masks_the_payment_secret():
    settings = Settings(payment_secret_key=SecretStr(SECRET))

    assert SECRET not in repr(settings)
    assert SECRET not in str(settings)
    # ...but the real value is still retrievable for the adapter that needs it.
    assert settings.payment_secret_key.get_secret_value() == SECRET


# --------------------------------------------------------------------------- factory selection


def test_factory_defaults_to_fake_when_unset():
    provider = build_payment_provider(Settings(payment_provider=""))

    assert isinstance(provider, FakePaymentProvider)


def test_factory_selects_fake_explicitly():
    provider = build_payment_provider(Settings(payment_provider="fake"))

    assert isinstance(provider, FakePaymentProvider)


def test_factory_selects_stripe_with_secret_and_base_url():
    settings = Settings(
        payment_provider="stripe",
        payment_secret_key=SecretStr(SECRET),
        stripe_base_url="https://api.stripe.test",
    )

    provider = build_payment_provider(settings)

    assert isinstance(provider, StripePaymentProvider)
    assert provider.base_url == "https://api.stripe.test"
    # The configured secret is threaded into the adapter, yet never surfaced in its repr.
    assert provider._secret_key == SECRET
    assert SECRET not in repr(provider)


def test_factory_selects_conekta_with_base_url():
    settings = Settings(
        payment_provider="conekta",
        payment_secret_key=SecretStr(SECRET),
        conekta_base_url="https://api.conekta.test",
    )

    provider = build_payment_provider(settings)

    assert isinstance(provider, ConektaPaymentProvider)
    assert provider.base_url == "https://api.conekta.test"


def test_factory_is_case_insensitive_and_trims_whitespace():
    settings = Settings(payment_provider="  Stripe ", payment_secret_key=SecretStr(SECRET))

    assert isinstance(build_payment_provider(settings), StripePaymentProvider)


def test_factory_rejects_an_unknown_provider():
    with pytest.raises(ValueError, match="Unknown COMMERCE_PAYMENT_PROVIDER"):
        build_payment_provider(Settings(payment_provider="paypal"))
