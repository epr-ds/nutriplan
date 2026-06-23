"""Tests for the locale-aware catalog and locale parsing (AIA-103, AC3)."""

import pytest

from app.prompts.catalog import InMemoryPromptCatalog, PromptCatalog
from app.prompts.errors import (
    DuplicatePromptError,
    PromptNotFoundError,
    UnknownLocaleError,
)
from app.prompts.template import PromptTemplate
from app.prompts.types import Locale


def _template(locale: Locale, *, prompt_id: str = "tip") -> PromptTemplate:
    return PromptTemplate(id=prompt_id, version="v1", locale=locale, user=f"tip in {locale.value}")


def test_get_returns_the_requested_locale() -> None:
    catalog = InMemoryPromptCatalog([_template(Locale.EN), _template(Locale.ES)])

    assert catalog.get("tip", Locale.ES).locale is Locale.ES
    assert catalog.get("tip", Locale.EN).locale is Locale.EN


def test_get_falls_back_to_default_locale() -> None:
    catalog = InMemoryPromptCatalog([_template(Locale.EN)])

    # Spanish was never registered; the English (default) template is served instead,
    # and its locale is reported so telemetry reflects what actually ran.
    fallback = catalog.get("tip", Locale.ES)

    assert fallback.locale is Locale.EN


def test_get_unknown_prompt_raises() -> None:
    catalog = InMemoryPromptCatalog([_template(Locale.EN)])

    with pytest.raises(PromptNotFoundError):
        catalog.get("missing", Locale.EN)


def test_duplicate_registration_is_rejected() -> None:
    catalog = InMemoryPromptCatalog([_template(Locale.EN)])

    with pytest.raises(DuplicatePromptError):
        catalog.register(_template(Locale.EN))


def test_catalog_reports_ids_and_locales() -> None:
    catalog = InMemoryPromptCatalog([_template(Locale.EN), _template(Locale.ES)])

    assert catalog.ids == frozenset({"tip"})
    assert catalog.available_locales("tip") == frozenset({Locale.EN, Locale.ES})


def test_in_memory_catalog_satisfies_the_port() -> None:
    assert isinstance(InMemoryPromptCatalog(), PromptCatalog)


def test_locale_parse_normalizes_region_and_case() -> None:
    assert Locale.parse("es-MX") is Locale.ES
    assert Locale.parse("EN_US") is Locale.EN
    assert Locale.parse(Locale.ES) is Locale.ES


def test_locale_parse_unknown_falls_back_or_raises() -> None:
    assert Locale.parse("fr", default=Locale.EN) is Locale.EN
    with pytest.raises(UnknownLocaleError):
        Locale.parse("fr")
