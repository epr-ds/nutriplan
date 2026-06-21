"""Access-token verification (DPL-102).

The Dietary service is a pure *resource server*: it does not issue tokens, it only verifies the
RS256 access tokens minted by the Identity service. Verification keys are resolved from Identity's
published JWKS (``/.well-known/jwks.json``) by the token's ``kid`` header, which keeps key rotation
a deploy-time concern of Identity alone.

The verifier depends on an abstract :class:`SigningKeyResolver` (satisfied in production by PyJWT's
``PyJWKClient``, and in tests by a static-key double), so the verification logic is unit-testable
without any network access.
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

    Validates the signature plus the ``aud``/``iss``/``exp`` claims, then projects the token onto a
    :class:`Principal`. Any failure is normalised to :class:`InvalidTokenError`.
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
