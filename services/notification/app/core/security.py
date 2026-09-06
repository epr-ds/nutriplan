"""Access-token verification for the in-app feed API (NTF-105).

Notification is a pure *resource server*: it never issues tokens, it only verifies the RS256
access tokens minted by Identity. Verification keys are resolved from Identity's published
JWKS (``/.well-known/jwks.json``) by the token's ``kid`` header, so key rotation stays a
deploy-time concern of Identity alone and this service needs no shared secret.

The verifier depends on an abstract :class:`SigningKeyResolver` (satisfied in production by
PyJWT's ``PyJWKClient`` and in tests by a static double), so the verification logic is
unit-testable with no network access. This mirrors Commerce and Dietary deliberately: three
resource servers that verified tokens three subtly different ways would be three different
attack surfaces, and a claim tightened in one would silently stay loose in the others.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import jwt

from app.core.principal import Principal


class InvalidTokenError(Exception):
    """Raised when a bearer token is missing, malformed, expired, or otherwise unverifiable."""


@runtime_checkable
class SigningKeyResolver(Protocol):
    """Resolves the signing key for a JWT (by its ``kid``). Implemented by ``jwt.PyJWKClient``."""

    def get_signing_key_from_jwt(self, token: str) -> Any: ...


@runtime_checkable
class TokenVerifier(Protocol):
    """Verifies an access token and returns its :class:`Principal`."""

    def verify(self, token: str) -> Principal: ...


class JwtTokenVerifier:
    """Verifies RS256 access tokens against a resolved JWKS signing key.

    Validates the signature plus the ``aud``/``iss``/``exp`` claims, then projects the token
    onto a :class:`Principal`. ``algorithms`` is pinned rather than read from the token: a
    verifier that trusted the header's ``alg`` would accept ``none``, or accept an HMAC token
    signed with the *public* key it publishes. Any failure is normalised to
    :class:`InvalidTokenError`, so a caller cannot tell an expired token from a forged one.
    """

    def __init__(
        self,
        *,
        key_resolver: SigningKeyResolver,
        issuer: str,
        audience: str,
        algorithms: tuple[str, ...] = ("RS256",),
    ) -> None:
        self._key_resolver = key_resolver
        self._issuer = issuer
        self._audience = audience
        self._algorithms = list(algorithms)

    def verify(self, token: str) -> Principal:
        try:
            signing_key = self._key_resolver.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=self._algorithms,
                audience=self._audience,
                issuer=self._issuer,
            )
        except Exception as exc:  # noqa: BLE001 - any verification failure is an invalid token
            raise InvalidTokenError(str(exc)) from exc

        subject = claims.get("sub")
        if not subject:
            raise InvalidTokenError("token is missing the 'sub' claim")
        return Principal(user_id=subject, email=claims.get("email"))
