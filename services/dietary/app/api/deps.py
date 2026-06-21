"""Composition root / dependency wiring for the API layer.

FastAPI's ``Depends`` is used as a lightweight DI container: each provider builds one collaborator
and declares what it needs, so the request handlers receive fully-assembled services and never new
up their own dependencies. Tests swap any layer via ``app.dependency_overrides``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.meal_plan_service import MealPlanService
from app.core.config import settings
from app.core.principal import Principal
from app.core.security import InvalidTokenError, JwtTokenVerifier, TokenVerifier
from app.domain.repositories import MealPlanRepository
from app.repositories.mongo_meal_plan_repository import MongoMealPlanRepository

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


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> Principal:
    """Resolve the authenticated caller from a Bearer token, or raise ``401``."""
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return verifier.verify(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_meal_plan_repository() -> MealPlanRepository:
    return MongoMealPlanRepository()


def get_meal_plan_service(
    repository: Annotated[MealPlanRepository, Depends(get_meal_plan_repository)],
) -> MealPlanService:
    return MealPlanService(repository)


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
MealPlanServiceDep = Annotated[MealPlanService, Depends(get_meal_plan_service)]
