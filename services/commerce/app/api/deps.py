"""Composition root / dependency wiring for the API layer.

FastAPI's ``Depends`` is used as a lightweight DI container: each provider builds one collaborator
and declares what it needs, so handlers receive fully-assembled services and never new up their own
dependencies. Tests swap any layer via ``app.dependency_overrides``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.adapters.http_meal_plan_provider import HttpMealPlanProvider
from app.application.create_order import CreateOrderService
from app.application.ports import MealPlanProvider
from app.core.config import settings
from app.core.principal import Principal
from app.core.security import InvalidTokenError, JwtTokenVerifier, TokenVerifier
from app.db.base import get_db
from app.domain.repositories import OrderRepository
from app.repositories.sql_order_repository import SqlOrderRepository

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


@lru_cache(maxsize=1)
def get_token_verifier() -> TokenVerifier:
    """Build the (cached) access-token verifier backed by Identity's JWKS endpoint."""
    jwks_client = jwt.PyJWKClient(settings.identity_jwks_url)
    return JwtTokenVerifier(
        key_resolver=jwks_client,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )


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


def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Expose the raw bearer token so it can be forwarded to Dietary (token relay)."""
    return _require_credentials(credentials).credentials


def get_order_repository(db: DbSession) -> OrderRepository:
    """Provide the SQL-backed order repository bound to the request session."""
    return SqlOrderRepository(db)


def get_meal_plan_provider() -> MealPlanProvider:
    """Provide the HTTP meal-plan provider (anti-corruption layer over Dietary)."""
    return HttpMealPlanProvider(
        base_url=settings.dietary_base_url, timeout=settings.http_timeout_seconds
    )


def get_create_order_service(
    orders: Annotated[OrderRepository, Depends(get_order_repository)],
    meal_plans: Annotated[MealPlanProvider, Depends(get_meal_plan_provider)],
) -> CreateOrderService:
    return CreateOrderService(orders, meal_plans)


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
BearerToken = Annotated[str, Depends(get_bearer_token)]
OrderRepositoryDep = Annotated[OrderRepository, Depends(get_order_repository)]
CreateOrderServiceDep = Annotated[CreateOrderService, Depends(get_create_order_service)]
