"""API-layer dependency wiring.

The AI service sits behind the gateway, which performs full JWT verification at the edge
(JWKS, reused from P1 — AIA-804). This slice (AIA-201) only enforces that a Bearer token is
*present*: a request without one is rejected with ``401`` before any work is done. Verifying the
token's signature/claims here is intentionally out of scope and tracked by AIA-804.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.analysis.service import MealAnalysisService, build_meal_analysis_service
from app.optimization.service import PlanOptimizationService, build_plan_optimization_service
from app.recommendations.service import RecommendationService, build_recommendation_service

_bearer = HTTPBearer(auto_error=False)


def require_bearer(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Require a Bearer credential, returning the raw token or raising ``401``."""
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


BearerToken = Annotated[str, Depends(require_bearer)]
RecommendationServiceDep = Annotated[RecommendationService, Depends(get_recommendation_service)]
MealAnalysisServiceDep = Annotated[MealAnalysisService, Depends(get_meal_analysis_service)]
PlanOptimizationServiceDep = Annotated[
    PlanOptimizationService, Depends(get_plan_optimization_service)
]
