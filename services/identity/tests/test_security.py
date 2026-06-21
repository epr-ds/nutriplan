import jwt
import pytest

from app.core import security


def test_password_hash_is_argon2id_and_verifies():
    hashed = security.hash_password("s3cret-password")
    assert hashed.startswith("$argon2id$")
    assert hashed != "s3cret-password"
    assert security.verify_password(hashed, "s3cret-password") is True
    assert security.verify_password(hashed, "wrong-password") is False


def test_access_token_roundtrip():
    token, ttl = security.create_access_token("user-123", "user@example.com")
    assert ttl == security.settings.access_token_ttl_seconds
    claims = security.decode_access_token(token)
    assert claims["sub"] == "user-123"
    assert claims["email"] == "user@example.com"
    assert claims["iss"] == security.settings.jwt_issuer


def test_tampered_token_is_rejected():
    token, _ = security.create_access_token("user-123", "user@example.com")
    with pytest.raises(jwt.InvalidTokenError):
        security.decode_access_token(token + "tampered")


def test_jwks_exposes_signing_key():
    jwks = security.build_jwks()
    key = jwks["keys"][0]
    assert key["kty"] == "RSA"
    assert key["use"] == "sig"
    assert key["alg"] == "RS256"
    assert key["kid"] == security.settings.jwt_kid
