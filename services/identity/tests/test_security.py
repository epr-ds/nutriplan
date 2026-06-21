import datetime as dt

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

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


# --- IDN-704: token attack surface at the HTTP boundary (GET /users/me) ---

_FAKE_SUB = "11111111-1111-1111-1111-111111111111"


def _claims(**overrides):
    now = dt.datetime.now(dt.UTC)
    base = {
        "sub": _FAKE_SUB,
        "email": "attacker@example.com",
        "iss": security.settings.jwt_issuer,
        "aud": security.settings.jwt_audience,
        "iat": now,
        "exp": now + dt.timedelta(seconds=600),
    }
    base.update(overrides)
    return base


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_users_me_rejects_foreign_key_signature(client):
    """A token signed by a key the service does not trust must not authenticate."""
    foreign_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        _claims(), foreign_key, algorithm="RS256", headers={"kid": security.settings.jwt_kid}
    )
    assert client.get("/users/me", headers=_auth(forged)).status_code == 401


def test_users_me_rejects_alg_none_token(client):
    """An unsigned (alg=none) token must be rejected — guards algorithm confusion."""
    unsigned = jwt.encode(_claims(), key="", algorithm="none")
    assert client.get("/users/me", headers=_auth(unsigned)).status_code == 401


def test_users_me_rejects_expired_token(client):
    """A correctly-signed but expired access token must be rejected."""
    expired = jwt.encode(
        _claims(exp=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=10)),
        security._private_key,
        algorithm="RS256",
    )
    assert client.get("/users/me", headers=_auth(expired)).status_code == 401


def test_users_me_rejects_wrong_audience(client):
    """A correctly-signed token minted for a different audience must be rejected."""
    wrong_aud = jwt.encode(
        _claims(aud="some-other-service"), security._private_key, algorithm="RS256"
    )
    assert client.get("/users/me", headers=_auth(wrong_aud)).status_code == 401


def test_users_me_rejects_malformed_bearer(client):
    assert client.get("/users/me", headers=_auth("not.a.jwt")).status_code == 401


def test_login_does_not_reveal_whether_email_exists(client):
    """Unknown email and wrong password are indistinguishable (no user enumeration)."""
    client.post(
        "/auth/register",
        json={"email": "real@example.com", "password": "supersecret", "name": "Real"},
    )
    unknown = client.post(
        "/auth/login", json={"email": "ghost@example.com", "password": "supersecret"}
    )
    wrong_pw = client.post(
        "/auth/login", json={"email": "real@example.com", "password": "nope-nope-nope"}
    )
    assert unknown.status_code == wrong_pw.status_code == 401
    assert unknown.json()["detail"] == wrong_pw.json()["detail"]
