"""Identity secrets provisioning (IDN-803).

The JWT signing keypair and the OAuth client secrets are secrets: they are injected per
environment from the secrets manager (stage/prod) and kept out of the rest of the runtime
config so they are masked in logs and reprs and never printed. Dev keeps the ephemeral keypair.
"""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from app.core.config import Settings


def provision_jwt_keypair(settings: Settings) -> tuple[RSAPrivateKey, RSAPublicKey]:
    """Resolve the JWT signing keypair for the environment (IDN-803).

    The vault-injected private key (``IDENTITY_JWT_PRIVATE_KEY``) signs and its public half
    verifies; an empty key in dev means an ephemeral keypair is generated, which is what dev
    uses until real keys are injected.
    """
    if settings.jwt_private_key.strip():
        private_key = serialization.load_pem_private_key(
            settings.jwt_private_key.encode(), password=None
        )
        return private_key, private_key.public_key()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def provision_oauth_client_secret(provider: str, settings: Settings) -> str | None:
    """Resolve the OAuth client id for ``provider`` from the environment's configuration."""
    raw = getattr(settings, f"{provider}_client_ids", "") or ""
    client_ids = [client_id.strip() for client_id in raw.split(",") if client_id.strip()]
    return client_ids[0] if client_ids else None
