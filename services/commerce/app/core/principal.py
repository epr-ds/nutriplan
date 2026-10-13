"""The authenticated caller (security principal)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """An authenticated caller, derived from a verified access token.

    ``user_id`` is the token ``sub`` claim (a UUID string minted by Identity) — the identifier the
    Commerce service uses to scope every order to its owner.
    """

    user_id: str
    email: str | None = None
