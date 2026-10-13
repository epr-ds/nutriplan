"""COM-102 security tests: RS256 access-token verification (no network, no DB).

A throwaway RSA keypair stands in for the Identity service's signing key; a static resolver plays
the role of ``PyJWKClient``. This exercises the real :class:`JwtTokenVerifier` decode path —
signature, audience, issuer, expiry, and the ``sub`` claim.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.security import InvalidTokenError, JwtTokenVerifier

ISSUER = "nutriplan-identity"
AUDIENCE = "nutriplan"


@pytest.fixture(scope="module")
def keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture
def verifier(keypair):
    _, public_key = keypair
    resolver = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=public_key)
    )
    return JwtTokenVerifier(key_resolver=resolver, issuer=ISSUER, audience=AUDIENCE)


def _token(
    private_key,
    *,
    sub="user-123",
    email="a@b.com",
    iss=ISSUER,
    aud=AUDIENCE,
    expires_in=900,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "email": email,
        "iss": iss,
        "aud": aud,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "nutriplan-dev"})


def test_verify_returns_principal(keypair, verifier):
    private_key, _ = keypair
    principal = verifier.verify(_token(private_key))
    assert principal.user_id == "user-123"
    assert principal.email == "a@b.com"


def test_verify_rejects_wrong_audience(keypair, verifier):
    private_key, _ = keypair
    with pytest.raises(InvalidTokenError):
        verifier.verify(_token(private_key, aud="some-other-service"))


def test_verify_rejects_wrong_issuer(keypair, verifier):
    private_key, _ = keypair
    with pytest.raises(InvalidTokenError):
        verifier.verify(_token(private_key, iss="evil-issuer"))


def test_verify_rejects_expired_token(keypair, verifier):
    private_key, _ = keypair
    with pytest.raises(InvalidTokenError):
        verifier.verify(_token(private_key, expires_in=-10))


def test_verify_rejects_bad_signature(verifier):
    foreign_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(InvalidTokenError):
        verifier.verify(_token(foreign_key))


def test_verify_rejects_missing_subject(keypair, verifier):
    private_key, _ = keypair
    with pytest.raises(InvalidTokenError):
        verifier.verify(_token(private_key, sub=None))


def test_verify_rejects_garbage(verifier):
    with pytest.raises(InvalidTokenError):
        verifier.verify("not-a-jwt")
