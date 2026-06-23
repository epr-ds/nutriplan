"""Tests for the shipped prompt library and the prompt->LLM bridge (AIA-103)."""

from app.llm.types import LLMRequest, Role
from app.prompts.library import (
    MEAL_RECOMMENDATION_ID,
    build_default_catalog,
    build_default_renderer,
)
from app.prompts.telemetry import InMemoryPromptTelemetry
from app.prompts.types import Locale

_VARIABLES = {
    "goal": "lose weight",
    "diet": "mediterranean",
    "allergies": "peanuts",
    "calories": 1800,
    "count": 3,
}


def test_meal_recommendation_ships_in_en_and_es() -> None:
    catalog = build_default_catalog()

    assert MEAL_RECOMMENDATION_ID in catalog.ids
    assert catalog.available_locales(MEAL_RECOMMENDATION_ID) == frozenset({Locale.EN, Locale.ES})


def test_localized_versions_match() -> None:
    catalog = build_default_catalog()

    en = catalog.get(MEAL_RECOMMENDATION_ID, Locale.EN)
    es = catalog.get(MEAL_RECOMMENDATION_ID, Locale.ES)

    assert en.version == es.version


def test_render_spanish_prompt_records_version() -> None:
    telemetry = InMemoryPromptTelemetry()
    renderer = build_default_renderer(telemetry=telemetry)

    rendered = renderer.render(MEAL_RECOMMENDATION_ID, locale="es", variables=_VARIABLES)

    assert "Sugiere 3 ideas de comidas" in rendered.messages[-1].content
    assert telemetry.records[0].locale is Locale.ES
    assert telemetry.records[0].version


def test_rendered_prompt_converts_to_llm_request() -> None:
    rendered = build_default_renderer(telemetry=None).render(
        MEAL_RECOMMENDATION_ID, locale=Locale.EN, variables=_VARIABLES
    )

    request = rendered.to_request(model="gpt-4o-mini")

    assert isinstance(request, LLMRequest)
    assert request.model == "gpt-4o-mini"
    assert [m.role for m in request.messages] == [Role.SYSTEM, Role.USER]
    assert "Suggest 3 meal ideas" in request.messages[-1].content
