"""Password hashing (Argon2id) and RS256 JWT issuance/verification + JWKS.

Signing keys come from configuration (the secrets manager in stage/prod, IDN-803). In
development, if no key is supplied an ephemeral 2048-bit RSA keypair is generated at import
time so the service is runnable out of the box — such tokens do not survive a restart.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2 import exceptions as argon2_exceptions
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from jwt.algorithms import RSAAlgorithm

from app.core.config import settings

logger = logging.getLogger(__name__)

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return an Argon2id hash for *password*."""
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Return True iff *password* matches *password_hash* (constant-time)."""
    try:
        _password_hasher.verify(password_hash, password)
        return True
    except argon2_exceptions.VerifyMismatchError:
        return False
    except argon2_exceptions.InvalidHashError:
        return False


def _load_keys() -> tuple[RSAPrivateKey, RSAPublicKey]:
    if settings.jwt_private_key.strip():
        private_key = serialization.load_pem_private_key(
            settings.jwt_private_key.encode(), password=None
        )
    else:
        logger.warning(
            "IDENTITY_JWT_PRIVATE_KEY not set; generating an ephemeral dev keypair. "
            "Tokens will not survive a restart. Do NOT use this in production."
        )
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    if not isinstance(private_key, RSAPrivateKey):  # pragma: no cover - defensive
        raise TypeError("IDENTITY_JWT_PRIVATE_KEY must be an RSA private key in PEM format")
    return private_key, private_key.public_key()


_private_key, _public_key = _load_keys()


def create_access_token(subject: str, email: str) -> tuple[str, int]:
    """Issue an RS256 access token for *subject*. Returns (token, expires_in_seconds)."""
    now = datetime.now(UTC)
    ttl = settings.access_token_ttl_seconds
    payload = {
        "sub": subject,
        "email": email,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
    }
    token = jwt.encode(payload, _private_key, algorithm="RS256", headers={"kid": settings.jwt_kid})
    return token, ttl


def decode_access_token(token: str) -> dict:
    """Decode and verify an RS256 access token. Raises jwt exceptions on failure."""
    return jwt.decode(
        token,
        _public_key,
        algorithms=["RS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )


def build_jwks() -> dict:
    """Return the public JWKS document for token verification by other services."""
    jwk = json.loads(RSAAlgorithm.to_jwk(_public_key))
    jwk.update({"kid": settings.jwt_kid, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}
