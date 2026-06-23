"""``POST /ai/recommendations`` — AI recipe recommendations (AIA-201).

This slice owns the transport edge: Bearer auth, request validation, and the
``AIRecommendationResponse`` envelope. The body is a validated stub — prompt assembly (AIA-202),
LLM call + recipe mapping (AIA-203), and nutritional alignment + reasoning (AIA-204) are layered on
top in later stories, behind this same route.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import BearerToken
from app.api.schemas import AIRecommendationRequest, AIRecommendationResponse

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/recommendations", response_model=AIRecommendationResponse)
def get_recommendations(
    request: AIRecommendationRequest,
    _token: BearerToken,
) -> AIRecommendationResponse:
    """Validate the request and return the (currently stubbed) recommendation envelope."""
    return AIRecommendationResponse()
