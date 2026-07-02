"""Provider contract tests for the AI service (AIA-702).

Verify that the AI service's *actual* responses conform to the published
``contracts/ai.openapi.yaml`` — every implemented operation is driven to each
response it documents (happy path + documented errors) and the real response is
validated against the contract with ``openapi-core``. A breaking change (renamed/
removed required field, changed type, drifted enum, undocumented status) makes a
test fail, which gates the PR in Backend CI (``backend.yml`` ai-service job).

The endpoints are exercised through the real routers/schemas, with the AI
services swapped for network-free, deterministic doubles via FastAPI
``dependency_overrides`` — so the suite needs no provider, database, or network,
exactly like the other AI API tests.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from openapi_core import Config, OpenAPI
from openapi_core.testing import MockRequest, MockResponse

from app.analysis.alignment import MealAligner, MealReference
from app.analysis.commands import MealAnalysisCommand
from app.analysis.result import AnalyzedNutrition, MealAnalysis
from app.api.deps import (
    get_meal_analysis_service,
    get_plan_optimization_service,
    get_recommendation_service,
)
from app.llm.client import LLMClient
from app.llm.fake import FakeLLMProvider
from app.llm.retry import RetryPolicy
from app.llm.types import LLMResponse
from app.main import app
from app.optimization.gateway import InMemoryPlanGateway
from app.optimization.plan import (
    NutritionTargets,
    OptimizationMeal,
    OptimizationPlan,
    PlanNutrition,
    PlanNutritionSummary,
)
from app.optimization.service import PlanOptimizationService
from app.recommendations.assembler import build_recommendation_prompt_assembler
from app.recommendations.catalogue import InMemoryRecipeCatalogue
from app.recommendations.draft import RecommendationDraft
from app.recommendations.mapper import RecipeMapper
from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)
from app.recommendations.service import RecommendationService
from app.structured.parser import StructuredOutputParser
from app.structured.service import StructuredCompletion

HOST = "http://localhost:8000"
TOKEN = "contract-token"
_AUTH = {"Authorization": f"Bearer {TOKEN}"}
_PROBLEM_JSON = "application/problem+json"
_PLAN_ID = "11111111-1111-1111-1111-111111111111"
_MISSING_PLAN_ID = "99999999-9999-9999-9999-999999999999"


def _locate_spec() -> Path | None:
    if env := os.getenv("AI_OPENAPI_SPEC"):
        candidate = Path(env)
        if candidate.is_file():
            return candidate
    # Walk up from this file (…/services/ai/tests) to the repo root, where the contract
    # lives at contracts/ai.openapi.yaml. Also covers a /contracts mount (compose).
    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / "contracts" / "ai.openapi.yaml"
        if candidate.is_file():
            return candidate
    return None


_SPEC_PATH = _locate_spec()

if _SPEC_PATH is None:
    # In CI the contract is always checked out, so a miss means the gate is mis-wired —
    # fail loudly. Locally (e.g. a bare in-image run without the contract mounted) skip.
    if os.getenv("CI"):
        raise RuntimeError(
            "Provider contract tests could not locate contracts/ai.openapi.yaml in CI. "
            "Set AI_OPENAPI_SPEC or ensure the contract is checked out."
        )
    pytest.skip(
        "ai.openapi.yaml not found; set AI_OPENAPI_SPEC or mount /contracts",
        allow_module_level=True,
    )


def _config() -> Config:
    # The service emits errors as ``application/problem+json`` (RFC 7807); teach openapi-core
    # to deserialize that media type so error bodies are validated against Problem.
    return Config(extra_media_type_deserializers={_PROBLEM_JSON: json.loads})


@pytest.fixture(scope="module")
def openapi() -> OpenAPI:
    return OpenAPI.from_file_path(str(_SPEC_PATH), config=_config())


# --- Deterministic service doubles ------------------------------------------


_DRAFT = {
    "recipes": [
        {
            "name": "Avena con Frutas",
            "description": "Desayuno rapido.",
            "ingredients": [{"name": "avena", "quantity": 80, "unit": "g"}],
            "instructions": ["Mezcla.", "Sirve."],
            "prep_time_minutes": 5,
            "cook_time_minutes": 0,
            "servings": 1,
            "nutrition": {"calories": 350, "protein": 12, "carbs": 60, "fat": 7, "sugar": 15},
            "dietary_types": ["vegetarian"],
        },
        {
            "name": "Tostada de Aguacate",
            "description": "Almuerzo ligero.",
            "ingredients": [
                {"name": "pan integral", "quantity": 2, "unit": "rebanadas"},
                {"name": "aguacate", "quantity": 1, "unit": "unidad"},
            ],
            "instructions": ["Tuesta el pan.", "Agrega el aguacate."],
            "prep_time_minutes": 8,
            "cook_time_minutes": 3,
            "servings": 1,
            "nutrition": {"calories": 420, "protein": 11, "carbs": 38, "fat": 26, "sugar": 4},
            "dietary_types": ["vegetarian", "vegan"],
        },
    ],
    "reasoning": "Estas recetas se ajustan a tu objetivo de 400 kcal.",
}


def _recommendation_service() -> RecommendationService:
    """A network-free recommendation service returning two real, mapped recipes."""
    provider = FakeLLMProvider([LLMResponse(content=json.dumps(_DRAFT), model="fake")])
    completion = StructuredCompletion(
        LLMClient(provider, RetryPolicy(max_retries=0)),
        StructuredOutputParser(RecommendationDraft),
        max_attempts=1,
    )
    linked = RecommendedRecipe(
        id="recipe-oatmeal",
        name="Avena con Frutas",
        servings=2,
        ingredients=(RecommendedIngredient(name="avena", quantity=70, unit="g"),),
        instructions=("Paso del catalogo.",),
        nutrition=RecommendedNutrition(calories=360, protein=13, carbs=58, fat=8),
        source=RecipeSource.CATALOGUE,
    )
    mapper = RecipeMapper(InMemoryRecipeCatalogue([linked]))
    return RecommendationService(build_recommendation_prompt_assembler(), completion, mapper)


class _FakeAnalysisService:
    """Returns a canned :class:`MealAnalysis` regardless of the command."""

    def __init__(self, result: MealAnalysis) -> None:
        self._result = result

    def analyze(self, command: MealAnalysisCommand) -> MealAnalysis:
        return self._result


def _analysis_service() -> _FakeAnalysisService:
    nutrition = AnalyzedNutrition(calories=500, protein=20, carbs=60, fat=18, sugar=12)
    alignment = MealAligner(
        reference=MealReference(calories=500, protein=20, carbs=60, fat=18, sugar=12)
    ).align(nutrition)
    return _FakeAnalysisService(
        MealAnalysis(
            nutrition=nutrition,
            alignment=alignment,
            warnings=("Contains a common allergen: peanuts.",),
            disclaimer="This information is AI-generated and is not medical advice.",
        )
    )


class _PassThroughOptimizer:
    def optimize(self, plan: OptimizationPlan, goal: object) -> OptimizationPlan:
        return plan


def _plan() -> OptimizationPlan:
    nutrition = PlanNutrition(calories=400, protein=20.5, carbs=45.0, fat=12.0, sugar=8.0)
    return OptimizationPlan(
        id=_PLAN_ID,
        name="Cutting Week",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        daily_calorie_target=2000,
        status="active",
        meals=(
            OptimizationMeal(id="m1", meal_type="breakfast", servings=1.5, nutrition=nutrition),
        ),
        nutritional_summary=PlanNutritionSummary(
            total=nutrition,
            daily_average=PlanNutrition(calories=57, protein=2.9, carbs=6.4, fat=1.7, sugar=1.1),
            targets=NutritionTargets(calories=2000, protein=150, carbs=200, fat=60, sugar=50),
        ),
    )


def _optimization_service(plan: OptimizationPlan | None = None) -> PlanOptimizationService:
    gateway = InMemoryPlanGateway()
    gateway.add(plan if plan is not None else _plan(), owner=TOKEN)
    return PlanOptimizationService(gateway=gateway, optimizer=_PassThroughOptimizer())


@pytest.fixture
def client():
    app.dependency_overrides[get_recommendation_service] = _recommendation_service
    app.dependency_overrides[get_meal_analysis_service] = _analysis_service
    app.dependency_overrides[get_plan_optimization_service] = lambda: _optimization_service()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def assert_conforms(openapi: OpenAPI, method: str, path: str, response) -> None:
    """Validate a captured TestClient response against the contract for method+path."""
    content_type = response.headers.get("content-type", "application/json").split(";")[0].strip()
    request = MockRequest(host_url=HOST, method=method.lower(), path=path)
    mock_response = MockResponse(
        data=response.content,
        status_code=response.status_code,
        content_type=content_type,
    )
    openapi.validate_response(request, mock_response)


# --- /ai/recommendations ----------------------------------------------------


def test_recommendations_conforms(openapi, client):
    # A per-meal calorie target makes the AIA-106 scorer emit a non-null nutritionalAlignment.
    resp = client.post(
        "/ai/recommendations",
        json={"context": "single_meal", "language": "es", "calorieTarget": 400},
        headers=_AUTH,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [r["name"] for r in body["recommendations"]] == [
        "Avena con Frutas",
        "Tostada de Aguacate",
    ]
    assert body["nutritionalAlignment"] is not None
    assert_conforms(openapi, "post", "/ai/recommendations", resp)


def test_recommendations_unauthenticated_conforms(openapi, client):
    resp = client.post("/ai/recommendations", json={"context": "meal_plan"})
    assert resp.status_code == 401
    assert resp.headers["content-type"].split(";")[0].strip() == _PROBLEM_JSON
    assert_conforms(openapi, "post", "/ai/recommendations", resp)


def test_recommendations_validation_error_conforms(openapi, client):
    resp = client.post("/ai/recommendations", json={"context": "not-a-context"}, headers=_AUTH)
    assert resp.status_code == 422
    assert_conforms(openapi, "post", "/ai/recommendations", resp)


# --- /ai/analyze-meal -------------------------------------------------------


def test_analyze_meal_conforms(openapi, client):
    resp = client.post(
        "/ai/analyze-meal", json={"description": "Oatmeal with peanuts"}, headers=_AUTH
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["nutritionalInfo"]["calories"] == 500
    assert body["alignment"] is not None
    assert_conforms(openapi, "post", "/ai/analyze-meal", resp)


def test_analyze_meal_empty_analysis_conforms(openapi, client):
    # An empty analysis projects nutritionalInfo + alignment as null — the contract allows it.
    app.dependency_overrides[get_meal_analysis_service] = lambda: _FakeAnalysisService(
        MealAnalysis()
    )
    resp = client.post("/ai/analyze-meal", json={"description": "Just water"}, headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["nutritionalInfo"] is None
    assert body["alignment"] is None
    assert_conforms(openapi, "post", "/ai/analyze-meal", resp)


def test_analyze_meal_unauthenticated_conforms(openapi, client):
    resp = client.post("/ai/analyze-meal", json={"description": "x"})
    assert resp.status_code == 401
    assert_conforms(openapi, "post", "/ai/analyze-meal", resp)


def test_analyze_meal_validation_error_conforms(openapi, client):
    # ``description`` is required.
    resp = client.post("/ai/analyze-meal", json={}, headers=_AUTH)
    assert resp.status_code == 422
    assert_conforms(openapi, "post", "/ai/analyze-meal", resp)


# --- /ai/optimize-plan ------------------------------------------------------


def test_optimize_plan_conforms(openapi, client):
    resp = client.post(
        "/ai/optimize-plan", json={"planId": _PLAN_ID, "goal": "balance_macros"}, headers=_AUTH
    )
    assert resp.status_code == 200
    body = resp.json()
    # Pass-through optimizer = no-op, so the draft proposes the original plan unchanged
    # (improve-or-no-op, AIA-404/405). Any documented status conforms; the point is the schema.
    assert body["status"] in {"draft", "active", "completed", "saved"}
    assert body["meals"][0]["recipe"] is None
    assert body["nutritionalSummary"]["targets"]["calories"] == 2000
    assert_conforms(openapi, "post", "/ai/optimize-plan", resp)


def test_optimize_plan_without_summary_conforms(openapi, client):
    # A plan with no meals projects nutritionalSummary as null — exercises the nullable summary.
    bare = OptimizationPlan(
        id=_PLAN_ID,
        name="Bare",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        daily_calorie_target=1800,
        status="draft",
    )
    app.dependency_overrides[get_plan_optimization_service] = lambda: _optimization_service(bare)
    resp = client.post("/ai/optimize-plan", json={"planId": _PLAN_ID}, headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meals"] == []
    assert body["nutritionalSummary"] is None
    assert_conforms(openapi, "post", "/ai/optimize-plan", resp)


def test_optimize_plan_not_found_conforms(openapi, client):
    resp = client.post("/ai/optimize-plan", json={"planId": _MISSING_PLAN_ID}, headers=_AUTH)
    assert resp.status_code == 404
    assert resp.headers["content-type"].split(";")[0].strip() == _PROBLEM_JSON
    assert_conforms(openapi, "post", "/ai/optimize-plan", resp)


def test_optimize_plan_unauthenticated_conforms(openapi, client):
    resp = client.post("/ai/optimize-plan", json={"planId": _PLAN_ID})
    assert resp.status_code == 401
    assert_conforms(openapi, "post", "/ai/optimize-plan", resp)


def test_optimize_plan_validation_error_conforms(openapi, client):
    resp = client.post("/ai/optimize-plan", json={"planId": "not-a-uuid"}, headers=_AUTH)
    assert resp.status_code == 422
    assert_conforms(openapi, "post", "/ai/optimize-plan", resp)


# --- Health -----------------------------------------------------------------


def test_health_conforms(openapi, client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert_conforms(openapi, "get", "/health", resp)


def test_readiness_conforms(openapi, client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert {check["name"] for check in resp.json()["checks"]} == {"llm_provider"}
    assert_conforms(openapi, "get", "/health/ready", resp)


# --- The gate actually catches drift (AIA-702 AC2) --------------------------


def test_a_breaking_change_fails_validation(client, tmp_path):
    """Prove the gate bites: a response missing a newly-required field must fail to conform.

    We mutate a copy of the contract to require a field the real response does not emit
    (a breaking change a producer might ship) and assert that validating the *real*
    recommendations response against the drifted contract raises.
    """
    spec = yaml.safe_load(_SPEC_PATH.read_text(encoding="utf-8"))
    response_schema = spec["components"]["schemas"]["AIRecommendationResponse"]
    response_schema["required"] = [
        *response_schema.get("required", []),
        "fieldAddedByABreakingChange",
    ]
    drifted_path = tmp_path / "ai.drifted.yaml"
    drifted_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    drifted = OpenAPI.from_file_path(str(drifted_path), config=_config())

    resp = client.post("/ai/recommendations", json={"context": "meal_plan"}, headers=_AUTH)
    assert resp.status_code == 200

    with pytest.raises(Exception):  # noqa: B017 - any openapi-core validation error is a pass here
        assert_conforms(drifted, "post", "/ai/recommendations", resp)
