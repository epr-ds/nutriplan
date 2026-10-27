"""API tests for the AI token-budget kill-switch surfacing (AIA-805 / AIA-105)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_recommendation_service
from app.budget.guard import TokenBudgetGuard
from app.budget.policy import BudgetPolicy, BudgetScope
from app.completions import CachedCompletionService
from app.kv.memory import InMemoryKeyValueStore
from app.llm.client import LLMClient
from app.llm.fake import FakeLLMProvider
from app.llm.retry import RetryPolicy
from app.llm.types import LLMResponse
from app.main import app
from app.recommendations.assembler import build_recommendation_prompt_assembler
from app.recommendations.catalogue import InMemoryRecipeCatalogue
from app.recommendations.draft import RecommendationDraft
from app.recommendations.mapper import RecipeMapper
from app.recommendations.service import RecommendationService
from app.structured.parser import StructuredOutputParser
from app.structured.service import StructuredCompletion

client = TestClient(app)

_AUTH = {"Authorization": "Bearer test-token"}
_PROBLEM_JSON = "application/problem+json"


def _budget_service() -> RecommendationService:
    provider = FakeLLMProvider([LLMResponse(content='{"recipes": []}', model="fake")])
    completion = StructuredCompletion(
        LLMClient(provider, RetryPolicy(max_retries=0)),
        StructuredOutputParser(RecommendationDraft),
        max_attempts=1,
    )
    guard = TokenBudgetGuard(
        InMemoryKeyValueStore(),
        BudgetPolicy(global_tokens=1, window_seconds=86_400),
    )
    guard.charge(BudgetScope(user_id="test-user", route="recommendations"), 10)
    return RecommendationService(
        build_recommendation_prompt_assembler(),
        CachedCompletionService(completion, guard=guard),
        RecipeMapper(InMemoryRecipeCatalogue()),
    )


@pytest.fixture
def override_recommendation_service():
    app.dependency_overrides[get_recommendation_service] = _budget_service
    yield
    app.dependency_overrides.pop(get_recommendation_service, None)


def test_global_kill_switch_returns_429_problem_json(
    override_recommendation_service,
) -> None:
    """When the global token budget trips, the endpoint refuses with ``429`` before spending."""
    response = client.post(
        "/ai/recommendations",
        json={"context": "meal_plan", "language": "es"},
        headers=_AUTH,
    )

    assert response.status_code == 429
    assert response.headers["content-type"].startswith(_PROBLEM_JSON)
    assert response.json()["status"] == 429
