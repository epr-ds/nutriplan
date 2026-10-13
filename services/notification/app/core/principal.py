"""The authenticated caller (security principal)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """An authenticated caller, derived from a verified access token.

    ``user_id`` is the token ``sub`` claim (a UUID string minted by Identity) -- the only
    identifier this service will scope a feed to. It is taken from the *token*, never from a
    path, query, or body parameter: an endpoint that accepted a user id from the request
    would let any authenticated caller read anyone's notifications, and no amount of
    store-level owner-scoping could save it.
    """

    user_id: str
    email: str | None = None
