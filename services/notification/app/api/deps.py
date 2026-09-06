"""Composition root / dependency wiring for the notification API (NTF-105).

FastAPI's ``Depends`` is used as a lightweight DI container: each provider builds one
collaborator and declares what it needs, so handlers receive fully-assembled services and
never new up their own dependencies. Tests swap any layer via ``app.dependency_overrides``.

The one thing to be careful about here is **caching the store**. Commerce rebuilds its
repository per request because it wraps a request-scoped SQL session; this service must not.
``build_notification_repository`` returns an *in-process* store whenever
``NOTIFICATION_REDIS_URL`` is blank -- the dev/CI default -- and that store holds all of its
state in the object. Building one per request would hand every request a brand-new, empty
feed, and the failure would look like "notifications vanish immediately" rather than like a
wiring mistake. Caching is right for the Redis adapter too: it reuses one connection pool
instead of opening a client per request.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.adapters.factory import build_notification_repository
from app.application.feed import NotificationFeed
from app.core.config import settings
from app.core.principal import Principal
from app.core.security import InvalidTokenError, JwtTokenVerifier, TokenVerifier
from app.domain.repositories import NotificationRepository

_bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_token_verifier() -> TokenVerifier:
    """Build the (cached) access-token verifier backed by Identity's JWKS endpoint."""
    jwks_client = jwt.PyJWKClient(settings.identity_jwks_url)
    return JwtTokenVerifier(
        key_resolver=jwks_client,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )


@lru_cache(maxsize=1)
def get_notification_repository() -> NotificationRepository:
    """Build the (cached) configured notification store. See the module docstring."""
    return build_notification_repository()


def get_notification_feed(
    repository: Annotated[NotificationRepository, Depends(get_notification_repository)],
) -> NotificationFeed:
    """Build the feed use cases over the configured store."""
    return NotificationFeed(repository)


def _require_credentials(
    credentials: HTTPAuthorizationCredentials | None,
) -> HTTPAuthorizationCredentials:
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> Principal:
    """Resolve the authenticated caller from a bearer token or raise ``401``."""
    creds = _require_credentials(credentials)
    try:
        return verifier.verify(creds.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user_id(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> uuid.UUID:
    """Resolve the caller's id from the verified token subject, or ``401`` if it is not a UUID.

    Every feed operation is scoped by this value and this value only, so a token whose
    ``sub`` is not a notification-store user id is rejected outright rather than coerced into
    something that would silently address the wrong feed.
    """
    try:
        return uuid.UUID(principal.user_id)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Token subject is not a valid user id"
        ) from exc


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]
NotificationFeedDep = Annotated[NotificationFeed, Depends(get_notification_feed)]
