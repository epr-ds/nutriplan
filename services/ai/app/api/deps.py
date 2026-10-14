"""API-layer dependency wiring.

The AI service sits behind the gateway and also verifies access tokens directly (AIA-804).
Verification uses Identity's JWKS endpoint to validate the RS256 signature plus ``aud``/``iss``/
``exp`` claims, then projects the token onto a :class:`Principal`. This defense-in-depth ensures
that even if the gateway misroutes an unauthenticated request, the service rejects it.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.analysis.service import MealAnalysisService, build_meal_analysis_service
from app.core.config import settings
from app.core.principal import Principal
from app.core.security import InvalidTokenError, JwtTokenVerifier, TokenVerifier
from app.optimization.service import PlanOptimizationService, build_plan_optimization_service
from app.recommendations.service import RecommendationService, build_recommendation_service

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
    """Resolve the authenticated caller from a Bearer token or raise ``401``."""
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


def get_raw_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Require a Bearer token, returning the raw string or raising ``401``."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


@lru_cache(maxsize=1)
def get_recommendation_service() -> RecommendationService:
    """Build the (cached) recommendation service from configuration.

    Memoized so the completion cache and token-budget counters persist across requests rather than
    being rebuilt per call. Tests swap the whole service via ``app.dependency_overrides``.
    """
    return build_recommendation_service()


@lru_cache(maxsize=1)
def get_meal_analysis_service() -> MealAnalysisService:
    """Build the (cached) meal-analysis service from configuration (AIA-301).

    Memoized for parity with the recommendation service so future collaborators (the AIA-302
    estimator and its cache) persist across requests. Tests swap it via ``dependency_overrides``.
    """
    return build_meal_analysis_service()


@lru_cache(maxsize=1)
def get_plan_optimization_service() -> PlanOptimizationService:
    """Build the (cached) plan-optimization service from configuration (AIA-401).

    Memoized for parity with the other AI services. Defaults to an empty plan gateway until the real
    dietary-service adapter lands (AIA-402); tests swap it via ``dependency_overrides``.
    """
    return build_plan_optimization_service()


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
RawBearerToken = Annotated[str, Depends(get_raw_bearer_token)]
RecommendationServiceDep = Annotated[RecommendationService, Depends(get_recommendation_service)]
MealAnalysisServiceDep = Annotated[MealAnalysisService, Depends(get_meal_analysis_service)]
PlanOptimizationServiceDep = Annotated[PlanOptimizationService, Depends(get_plan_optimization_service)]