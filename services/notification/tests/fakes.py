"""Test doubles for the notification API suite."""

from __future__ import annotations

from app.core.principal import Principal
from app.core.security import InvalidTokenError


class StubVerifier:
    """Maps known tokens to principals; anything else is an invalid token.

    Standing in for the JWKS-backed verifier keeps the API tests off the network and lets
    them mint a second identity trivially, which is what the ownership tests need. The real
    decode path is covered separately in ``test_security.py`` against a throwaway RSA keypair,
    so nothing is left untested by this substitution.
    """

    def __init__(self, principals: dict[str, Principal]) -> None:
        self._principals = principals

    def verify(self, token: str) -> Principal:
        try:
            return self._principals[token]
        except KeyError as exc:
            raise InvalidTokenError("unknown token") from exc
