"""OAuth identity-token verification (IDN-201 Google, IDN-202 Apple).

Verifies a provider-issued OpenID Connect ``id_token`` (signature via the provider's
rotating JWKS, plus ``aud``/``iss``/``exp`` and — for Apple — ``nonce``) and returns the
normalized claims the Identity service needs to provision or look up a user.

Network JWKS fetching is isolated behind ``key_resolver`` so the verification logic can be
unit-tested with a locally minted key.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from app.core.config import settings

SUPPORTED_PROVIDERS = ("google", "apple")


class OAuthError(Exception):
    """Raised when an id-token cannot be trusted."""


@dataclass(frozen=True)
class OAuthClaims:
    subject: str
    email: str | None
    email_verified: bool
    name: str | None


@dataclass(frozen=True)
class _ProviderConfig:
    name: str
    issuers: tuple[str, ...]
    jwks_uri: str
    audiences: tuple[str, ...]
    requires_nonce: bool


def _split_ids(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _provider_config(provider: str) -> _ProviderConfig | None:
    if provider == "google":
        return _ProviderConfig(
            name="google",
            issuers=("accounts.google.com", "https://accounts.google.com"),
            jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
            audiences=_split_ids(settings.google_client_ids),
            requires_nonce=False,
        )
    if provider == "apple":
        return _ProviderConfig(
            name="apple",
            issuers=("https://appleid.apple.com",),
            jwks_uri="https://appleid.apple.com/auth/keys",
            audiences=_split_ids(settings.apple_client_ids),
            requires_nonce=True,
        )
    return None


def provider_supported(provider: str) -> bool:
    return provider in SUPPORTED_PROVIDERS


_jwks_clients: dict[str, PyJWKClient] = {}


def _default_key_resolver(cfg: _ProviderConfig, id_token: str):
    """Resolve the signing key from the provider JWKS (cached; handles key rotation)."""
    client = _jwks_clients.get(cfg.name)
    if client is None:
        client = PyJWKClient(cfg.jwks_uri)
        _jwks_clients[cfg.name] = client
    return client.get_signing_key_from_jwt(id_token).key


def _as_bool(value: object) -> bool:
    """Coerce a claim that may be a bool or a string (Apple sends ``"true"``/``"false"``)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _nonce_matches(claim: str | None, provided: str) -> bool:
    if not claim or not provided:
        return False
    if claim == provided:
        return True
    return claim == hashlib.sha256(provided.encode()).hexdigest()


def verify_oauth_token(
    provider: str,
    id_token: str,
    nonce: str | None = None,
    *,
    key_resolver=_default_key_resolver,
) -> OAuthClaims:
    """Verify *id_token* for *provider* and return its trusted claims, or raise ``OAuthError``."""
    cfg = _provider_config(provider)
    if cfg is None:
        raise OAuthError(f"Unsupported OAuth provider: {provider}")
    if not cfg.audiences:
        raise OAuthError(f"OAuth provider '{provider}' is not configured")

    try:
        key = key_resolver(cfg, id_token)
        claims = jwt.decode(id_token, key, algorithms=["RS256"], audience=list(cfg.audiences))
    except OAuthError:
        raise
    except Exception as exc:  # noqa: BLE001 - any verification failure is untrusted
        raise OAuthError("Invalid identity token") from exc

    if claims.get("iss") not in cfg.issuers:
        raise OAuthError("Untrusted token issuer")

    if cfg.requires_nonce and not _nonce_matches(claims.get("nonce"), nonce or ""):
        raise OAuthError("Nonce mismatch")

    subject = claims.get("sub")
    if not subject:
        raise OAuthError("Token is missing a subject")

    return OAuthClaims(
        subject=subject,
        email=(claims.get("email") or None),
        email_verified=_as_bool(claims.get("email_verified", False)),
        name=claims.get("name"),
    )
