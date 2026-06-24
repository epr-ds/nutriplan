"""Unit tests for the analyze-meal prompt assembler (AIA-302).

The assembler maps a :class:`MealAnalysisCommand` onto the localized ``analyze_meal`` template,
injecting the free-text description and a readable rendering of any structured ingredients (with
their nutrition hints) so the model can sharpen its estimate. It mirrors the recommendation
assembler: one place owns localization and the neutral fillers for absent fields.
"""

from __future__ import annotations

from app.analysis.assembler import build_meal_analysis_prompt_assembler
from app.analysis.commands import MealAnalysisCommand, MealIngredient
from app.llm.types import Role


def _user_text(prompt) -> str:
    return next(m.content for m in prompt.messages if m.role is Role.USER)


def test_injects_the_description() -> None:
    assembler = build_meal_analysis_prompt_assembler()

    prompt = assembler.assemble(MealAnalysisCommand(description="Oatmeal with banana"))

    assert "Oatmeal with banana" in _user_text(prompt)


def test_renders_structured_ingredients_with_hints() -> None:
    assembler = build_meal_analysis_prompt_assembler()
    command = MealAnalysisCommand(
        description="Breakfast bowl",
        ingredients=(
            MealIngredient(name="oats", quantity=80, unit="g", calories=300, protein=10),
            MealIngredient(name="banana"),
        ),
    )

    text = _user_text(assembler.assemble(command))

    assert "oats" in text
    assert "80" in text and "g" in text
    assert "300" in text  # the calorie hint reaches the model
    assert "banana" in text


def test_uses_a_filler_when_no_ingredients_are_given() -> None:
    assembler = build_meal_analysis_prompt_assembler()

    text = _user_text(assembler.assemble(MealAnalysisCommand(description="A snack")))

    assert "none" in text.lower()


def test_selects_the_spanish_template() -> None:
    assembler = build_meal_analysis_prompt_assembler()

    prompt = assembler.assemble(MealAnalysisCommand(description="Avena"), locale="es")

    assert any(
        m.role is Role.SYSTEM and "dietista-nutricionista" in m.content for m in prompt.messages
    )
