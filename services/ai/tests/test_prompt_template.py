"""Pure tests for PromptTemplate rendering and variable handling (AIA-103, AC1)."""

import pytest

from app.llm.types import Role
from app.prompts.errors import MissingPromptVariableError
from app.prompts.template import PromptTemplate
from app.prompts.types import Locale

_TEMPLATE = PromptTemplate(
    id="greeting",
    version="v1",
    locale=Locale.EN,
    system="You are $persona. Reply in $language.",
    user="Greet $name warmly.",
)


def test_render_emits_system_then_user_messages() -> None:
    rendered = _TEMPLATE.render({"persona": "a coach", "language": "English", "name": "Ada"})

    assert [m.role for m in rendered.messages] == [Role.SYSTEM, Role.USER]
    assert rendered.messages[0].content == "You are a coach. Reply in English."
    assert rendered.messages[1].content == "Greet Ada warmly."


def test_render_records_template_ref() -> None:
    rendered = _TEMPLATE.render({"persona": "a coach", "language": "English", "name": "Ada"})

    assert rendered.ref.id == "greeting"
    assert rendered.ref.version == "v1"
    assert rendered.ref.locale is Locale.EN


def test_required_variables_span_system_and_user() -> None:
    assert _TEMPLATE.required_variables() == frozenset({"persona", "language", "name"})


def test_missing_variable_raises_listing_the_names() -> None:
    with pytest.raises(MissingPromptVariableError) as exc:
        _TEMPLATE.render({"persona": "a coach"})

    message = str(exc.value)
    assert "language" in message and "name" in message
    assert "persona" not in message


def test_extra_variables_are_ignored() -> None:
    rendered = _TEMPLATE.render(
        {"persona": "a coach", "language": "English", "name": "Ada", "unused": "x"}
    )

    assert rendered.messages[1].content == "Greet Ada warmly."


def test_non_string_values_are_stringified() -> None:
    template = PromptTemplate(id="count", version="v1", locale=Locale.EN, user="You have $n items.")

    rendered = template.render({"n": 3})

    assert rendered.messages[0].content == "You have 3 items."


def test_blank_system_is_omitted() -> None:
    template = PromptTemplate(id="bare", version="v1", locale=Locale.EN, user="Just $do it.")

    rendered = template.render({"do": "do"})

    assert [m.role for m in rendered.messages] == [Role.USER]
