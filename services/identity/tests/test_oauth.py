import datetime as dt
import hashlib

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from app.core import oauth
from app.core.config import settings
from app.db.models import OAuthIdentity, User
from app.services import auth_service


@pytest.fixture
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _id_token(
    key,
    *,
    aud,
    iss,
    sub="oauth-sub-1",
    email="oauth@example.com",
    nonce=None,
    expired=False,
    name="OAuth User",
):
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": sub,
        "email": email,
        "email_verified": True,
        "name": name,
        "aud": aud,
        "iss": iss,
        "iat": now,
        "exp": now + dt.timedelta(seconds=-10 if expired else 600),
    }
    if nonce is not None:
        payload["nonce"] = nonce
    return jwt.encode(payload, key, algorithm="RS256")


# --- verifier unit tests: mint a token locally and inject the public key (no network) ---


def test_verify_google_token_ok(rsa_key, monkeypatch):
    monkeypatch.setattr(settings, "google_client_ids", "client-123")
    token = _id_token(rsa_key, aud="client-123", iss="https://accounts.google.com")
    claims = oauth.verify_oauth_token(
        "google", token, key_resolver=lambda cfg, t: rsa_key.public_key()
    )
    assert claims.subject == "oauth-sub-1"
    assert claims.email == "oauth@example.com"


def test_verify_rejects_wrong_audience(rsa_key, monkeypatch):
    monkeypatch.setattr(settings, "google_client_ids", "client-123")
    token = _id_token(rsa_key, aud="someone-else", iss="https://accounts.google.com")
    with pytest.raises(oauth.OAuthError):
        oauth.verify_oauth_token("google", token, key_resolver=lambda cfg, t: rsa_key.public_key())


def test_verify_rejects_expired(rsa_key, monkeypatch):
    monkeypatch.setattr(settings, "google_client_ids", "client-123")
    token = _id_token(rsa_key, aud="client-123", iss="https://accounts.google.com", expired=True)
    with pytest.raises(oauth.OAuthError):
        oauth.verify_oauth_token("google", token, key_resolver=lambda cfg, t: rsa_key.public_key())


def test_verify_rejects_untrusted_issuer(rsa_key, monkeypatch):
    monkeypatch.setattr(settings, "google_client_ids", "client-123")
    token = _id_token(rsa_key, aud="client-123", iss="https://evil.example.com")
    with pytest.raises(oauth.OAuthError):
        oauth.verify_oauth_token("google", token, key_resolver=lambda cfg, t: rsa_key.public_key())


def test_verify_apple_requires_matching_nonce(rsa_key, monkeypatch):
    monkeypatch.setattr(settings, "apple_client_ids", "app.bundle.id")
    token = _id_token(
        rsa_key, aud="app.bundle.id", iss="https://appleid.apple.com", nonce="nonce-abc"
    )
    ok = oauth.verify_oauth_token(
        "apple", token, "nonce-abc", key_resolver=lambda cfg, t: rsa_key.public_key()
    )
    assert ok.subject == "oauth-sub-1"
    with pytest.raises(oauth.OAuthError):
        oauth.verify_oauth_token(
            "apple", token, "wrong-nonce", key_resolver=lambda cfg, t: rsa_key.public_key()
        )


def test_verify_apple_accepts_hashed_nonce(rsa_key, monkeypatch):
    monkeypatch.setattr(settings, "apple_client_ids", "app.bundle.id")
    raw = "raw-nonce"
    token = _id_token(
        rsa_key,
        aud="app.bundle.id",
        iss="https://appleid.apple.com",
        nonce=hashlib.sha256(raw.encode()).hexdigest(),
    )
    claims = oauth.verify_oauth_token(
        "apple", token, raw, key_resolver=lambda cfg, t: rsa_key.public_key()
    )
    assert claims.subject == "oauth-sub-1"


def test_verify_unconfigured_provider_raises(rsa_key, monkeypatch):
    monkeypatch.setattr(settings, "google_client_ids", "")
    token = _id_token(rsa_key, aud="x", iss="https://accounts.google.com")
    with pytest.raises(oauth.OAuthError):
        oauth.verify_oauth_token("google", token, key_resolver=lambda cfg, t: rsa_key.public_key())


def test_verify_facebook_token_ok(rsa_key, monkeypatch):
    monkeypatch.setattr(settings, "facebook_client_ids", "fb-app-1")
    token = _id_token(rsa_key, aud="fb-app-1", iss="https://www.facebook.com")
    claims = oauth.verify_oauth_token(
        "facebook", token, key_resolver=lambda cfg, t: rsa_key.public_key()
    )
    assert claims.subject == "oauth-sub-1"
    assert claims.email == "oauth@example.com"


def test_verify_facebook_rejects_wrong_audience(rsa_key, monkeypatch):
    monkeypatch.setattr(settings, "facebook_client_ids", "fb-app-1")
    token = _id_token(rsa_key, aud="someone-else", iss="https://www.facebook.com")
    with pytest.raises(oauth.OAuthError):
        oauth.verify_oauth_token(
            "facebook", token, key_resolver=lambda cfg, t: rsa_key.public_key()
        )


# --- endpoint / provisioning tests: stub the verifier so no keys/network are needed ---


def _stub(monkeypatch, *, subject, email, name="OAuth User", email_verified=True):
    claims = oauth.OAuthClaims(
        subject=subject, email=email, email_verified=email_verified, name=name
    )
    monkeypatch.setattr(auth_service, "verify_oauth_token", lambda *a, **k: claims)


def test_oauth_login_provisions_new_user(client, monkeypatch):
    _stub(monkeypatch, subject="sub-google-1", email="newg@example.com")
    response = client.post("/auth/oauth/google", json={"idToken": "x"})
    assert response.status_code == 200
    body = response.json()
    assert body["accessToken"] and body["refreshToken"]
    assert body["user"]["email"] == "newg@example.com"


def test_oauth_login_idempotent_for_same_subject(client, monkeypatch):
    _stub(monkeypatch, subject="sub-google-2", email="repeat@example.com")
    first = client.post("/auth/oauth/google", json={"idToken": "x"}).json()
    second = client.post("/auth/oauth/google", json={"idToken": "x"}).json()
    assert first["user"]["id"] == second["user"]["id"]


def test_oauth_login_links_existing_email(client, monkeypatch):
    client.post(
        "/auth/register",
        json={"email": "linkme@example.com", "password": "supersecret", "name": "Link"},
    )
    _stub(monkeypatch, subject="sub-apple-1", email="linkme@example.com")
    response = client.post("/auth/oauth/apple", json={"idToken": "x", "nonce": "n"})
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "linkme@example.com"


def test_oauth_login_invalid_token_unauthorized(client, monkeypatch):
    def boom(*args, **kwargs):
        raise oauth.OAuthError("bad token")

    monkeypatch.setattr(auth_service, "verify_oauth_token", boom)
    response = client.post("/auth/oauth/google", json={"idToken": "bad"})
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


def test_oauth_login_provisions_via_facebook(client, monkeypatch):
    _stub(monkeypatch, subject="sub-fb-1", email="newfb@example.com")
    response = client.post("/auth/oauth/facebook", json={"idToken": "x"})
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "newfb@example.com"


def test_oauth_login_unsupported_provider(client):
    response = client.post("/auth/oauth/twitter", json={"idToken": "x"})
    assert response.status_code == 400


# --- IDN-204: cross-provider dedupe / account linking by verified email ---


def test_apple_string_email_verified_is_normalized(rsa_key, monkeypatch):
    """Apple encodes email_verified as the string "true"/"false" — it must be coerced to bool."""
    monkeypatch.setattr(settings, "apple_client_ids", "app.bundle.id")
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": "apple-sub",
        "email": "a@example.com",
        "email_verified": "false",
        "aud": "app.bundle.id",
        "iss": "https://appleid.apple.com",
        "iat": now,
        "exp": now + dt.timedelta(seconds=600),
        "nonce": "n",
    }
    token = jwt.encode(payload, rsa_key, algorithm="RS256")
    claims = oauth.verify_oauth_token(
        "apple", token, "n", key_resolver=lambda cfg, t: rsa_key.public_key()
    )
    assert claims.email_verified is False


def test_second_provider_same_verified_email_links_one_account(client, db_session, monkeypatch):
    shared = "shared@example.com"
    _stub(monkeypatch, subject="g-sub", email=shared)
    first = client.post("/auth/oauth/google", json={"idToken": "x"}).json()

    _stub(monkeypatch, subject="a-sub", email=shared)
    second = client.post("/auth/oauth/apple", json={"idToken": "x", "nonce": "n"}).json()

    assert first["user"]["id"] == second["user"]["id"]
    user = db_session.scalar(select(User).where(User.email == shared))
    providers = {
        i.provider
        for i in db_session.scalars(
            select(OAuthIdentity).where(OAuthIdentity.user_id == user.id)
        ).all()
    }
    assert providers == {"google", "apple"}


def test_unverified_email_collision_does_not_link(client, db_session, monkeypatch):
    client.post(
        "/auth/register",
        json={"email": "owner@example.com", "password": "supersecret", "name": "Owner"},
    )
    _stub(monkeypatch, subject="a-sub", email="owner@example.com", email_verified=False)
    response = client.post("/auth/oauth/apple", json={"idToken": "x", "nonce": "n"})

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert db_session.scalar(select(OAuthIdentity)) is None


def test_unverified_email_without_collision_provisions(client, db_session, monkeypatch):
    _stub(monkeypatch, subject="g-sub", email="fresh@example.com", email_verified=False)
    response = client.post("/auth/oauth/google", json={"idToken": "x"})

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "fresh@example.com"
    assert db_session.scalar(select(OAuthIdentity)) is not None
