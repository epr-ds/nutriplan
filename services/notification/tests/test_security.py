"""NTF-105 security tests: RS256 access-token verification (no network).

A throwaway RSA keypair stands in for the Identity service's signing key; a static resolver
plays the role of ``PyJWKClient``. This exercises the real :class:`JwtTokenVerifier` decode
path -- signature, audience, issuer, expiry, and the ``sub`` claim -- so the stub used by the
API tests never hides a verification bug.
"""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
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


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _forge_hs256(claims: dict, secret: bytes) -> str:
    """Hand-roll an HS256 token, bypassing PyJWT's encoder.

    ``jwt.encode`` refuses to sign with a PEM key at all -- a guard on the *minting* side.
    An attacker has no such guard, so the forgery is assembled here the way a real one would
    arrive: three base64url segments and a raw HMAC over the first two.
    """
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps(claims).encode())
    signing_input = f"{header}.{body}".encode()
    signature = _b64(hmac.new(secret, signing_input, hashlib.sha256).digest())
    return f"{header}.{body}.{signature}"


def test_verify_rejects_a_token_signed_with_an_unexpected_algorithm(keypair, verifier):
    """An HS256 token HMAC'd with the *public* key must not verify.

    This is the classic algorithm-confusion attack: a verifier that trusted the token
    header's ``alg`` would HMAC-verify using the very key it publishes to the world, and
    anyone could mint tokens for any user. The algorithm list is pinned to RS256, so the
    forgery is refused even though every claim in it is correct and its signature checks out
    under the algorithm it names.
    """
    _, public_key = keypair
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    now = datetime.now(UTC)
    forged = _forge_hs256(
        {
            "sub": "user-123",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=900)).timestamp()),
        },
        public_pem,
    )

    with pytest.raises(InvalidTokenError):
        verifier.verify(forged)
