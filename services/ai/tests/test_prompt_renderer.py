"""Tests for PromptRenderer: locale resolution + version telemetry (AIA-103, AC2)."""

from app.prompts.catalog import InMemoryPromptCatalog
from app.prompts.renderer import PromptRenderer
from app.prompts.telemetry import InMemoryPromptTelemetry
from app.prompts.template import PromptTemplate
from app.prompts.types import Locale

_EN = PromptTemplate(id="tip", version="v3", locale=Locale.EN, user="EN $topic")
_ES = PromptTemplate(id="tip", version="v3", locale=Locale.ES, user="ES $topic")


def _renderer(telemetry: InMemoryPromptTelemetry | None = None) -> PromptRenderer:
    return PromptRenderer(InMemoryPromptCatalog([_EN, _ES]), telemetry=telemetry)


def test_render_resolves_and_substitutes() -> None:
    rendered = _renderer().render("tip", locale=Locale.ES, variables={"topic": "fiber"})

    assert rendered.messages[0].content == "ES fiber"
    assert rendered.ref.locale is Locale.ES


def test_render_records_version_on_each_call() -> None:
    telemetry = InMemoryPromptTelemetry()
    renderer = _renderer(telemetry)

    renderer.render("tip", locale=Locale.EN, variables={"topic": "a"})
    renderer.render("tip", locale=Locale.ES, variables={"topic": "b"})

    assert telemetry.versions == ["v3", "v3"]
    assert [r.locale for r in telemetry.records] == [Locale.EN, Locale.ES]


def test_render_accepts_a_locale_string() -> None:
    rendered = _renderer().render("tip", locale="es-AR", variables={"topic": "x"})

    assert rendered.ref.locale is Locale.ES


def test_unknown_locale_falls_back_to_default() -> None:
    telemetry = InMemoryPromptTelemetry()

    rendered = _renderer(telemetry).render("tip", locale="fr", variables={"topic": "x"})

    assert rendered.ref.locale is Locale.EN
    assert telemetry.records[0].locale is Locale.EN


def test_render_without_telemetry_is_a_noop() -> None:
    rendered = _renderer(None).render("tip", locale=Locale.EN, variables={"topic": "x"})

    assert rendered.messages[0].content == "EN x"
