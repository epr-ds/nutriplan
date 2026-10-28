"""IDN-803: per-environment JWT signing key + OAuth client secret provisioning."""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from app.core.config import Settings
from app.core.provisioning import provision_jwt_keypair, provision_oauth_client_secret


def _rsa_pem(private_key: rsa.RSAPrivateKey) -> str:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def test_provision_jwt_keypair_uses_the_vault_injected_key() -> None:
    """IDN-803: the vault-injected JWT signing key is used in stage/prod."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings(environment="staging", jwt_private_key=_rsa_pem(key), jwt_kid="staging-kid")

    private_key, public_key = provision_jwt_keypair(settings)

    assert isinstance(private_key, RSAPrivateKey)
    assert isinstance(public_key, RSAPublicKey)
    assert private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ) == key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def test_provision_jwt_keypair_generates_an_ephemeral_dev_keypair_when_unconfigured() -> None:
    """IDN-803: dev runs on the ephemeral keypair until real keys are injected from the vault."""
    private_key, public_key = provision_jwt_keypair(Settings(environment="development"))

    assert isinstance(private_key, RSAPrivateKey)
    assert isinstance(public_key, RSAPublicKey)


def test_provision_oauth_client_secret_returns_the_configured_client_id() -> None:
    """IDN-803: the OAuth client id is resolved per environment from configuration."""
    settings = Settings(google_client_ids="client-a,client-b")

    assert provision_oauth_client_secret("google", settings) == "client-a"
