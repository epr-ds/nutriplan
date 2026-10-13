"""Tests for mapping LLM output onto recommended recipes (AIA-203).

The mapper turns a validated :class:`RecommendationDraft` into ``RecommendedRecipe`` results,
**linking** each drafted recipe to a real catalogue entry where the name matches (AC1) and
otherwise **synthesizing** a complete recipe from the model's own output (AC2/AC3). Either way every
result carries ingredients, steps, and nutrition.
"""

from __future__ import annotations

from app.recommendations.catalogue import InMemoryRecipeCatalogue
from app.recommendations.draft import (
    IngredientDraft,
    NutritionDraft,
    RecipeDraft,
    RecommendationDraft,
)
from app.recommendations.mapper import RecipeMapper
from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)


def _draft_recipe(name: str = "Grilled Salmon", **overrides: object) -> RecipeDraft:
    base: dict[str, object] = {
        "name": name,
        "description": "A simple dish.",
        "ingredients": [IngredientDraft(name="salmon", quantity=200, unit="g")],
        "instructions": ["Season the salmon.", "Grill for six minutes."],
        "prep_time_minutes": 10,
        "cook_time_minutes": 12,
        "servings": 2,
        "nutrition": NutritionDraft(calories=420, protein=38, carbs=2, fat=28, sugar=0),
        "dietary_types": ["paleo", "keto"],
    }
    base.update(overrides)
    return RecipeDraft(**base)


def _catalogue_recipe(name: str, *, recipe_id: str) -> RecommendedRecipe:
    return RecommendedRecipe(
        id=recipe_id,
        name=name,
        servings=4,
        ingredients=(RecommendedIngredient(name="catalogue salmon", quantity=180, unit="g"),),
        instructions=("Catalogue step.",),
        nutrition=RecommendedNutrition(calories=400, protein=35, carbs=3, fat=25),
        source=RecipeSource.CATALOGUE,
    )


def test_links_to_catalogue_recipe_when_name_matches() -> None:
    linked = _catalogue_recipe("Grilled Salmon", recipe_id="recipe-salmon")
    mapper = RecipeMapper(InMemoryRecipeCatalogue([linked]))

    result = mapper.map(RecommendationDraft(recipes=[_draft_recipe(name="grilled salmon")]))

    assert len(result) == 1
    assert result[0] is linked
    assert result[0].id == "recipe-salmon"
    assert result[0].source is RecipeSource.CATALOGUE


def test_synthesizes_when_no_catalogue_match() -> None:
    mapper = RecipeMapper(InMemoryRecipeCatalogue())

    [recipe] = mapper.map(RecommendationDraft(recipes=[_draft_recipe(name="Grilled Salmon")]))

    assert recipe.source is RecipeSource.SYNTHESIZED
    assert recipe.name == "Grilled Salmon"
    assert recipe.id == "grilled-salmon"


def test_synthesized_recipe_carries_full_detail() -> None:
    mapper = RecipeMapper(InMemoryRecipeCatalogue())

    [recipe] = mapper.map(RecommendationDraft(recipes=[_draft_recipe()]))

    # AC2/AC3: ingredients, steps, and nutrition all survive the mapping.
    assert recipe.ingredients == (RecommendedIngredient(name="salmon", quantity=200, unit="g"),)
    assert recipe.instructions == ("Season the salmon.", "Grill for six minutes.")
    assert recipe.nutrition == RecommendedNutrition(
        calories=420, protein=38, carbs=2, fat=28, sugar=0
    )
    assert recipe.servings == 2
    assert recipe.dietary_types == ("paleo", "keto")


def test_slugifies_a_messy_name() -> None:
    mapper = RecipeMapper(InMemoryRecipeCatalogue())

    [recipe] = mapper.map(
        RecommendationDraft(recipes=[_draft_recipe(name="  Grilled Salmon & Greens!  ")])
    )

    assert recipe.id == "grilled-salmon-greens"


def test_maps_a_mix_of_linked_and_synthesized_in_order() -> None:
    linked = _catalogue_recipe("Oatmeal Bowl", recipe_id="recipe-oatmeal")
    mapper = RecipeMapper(InMemoryRecipeCatalogue([linked]))

    result = mapper.map(
        RecommendationDraft(
            recipes=[
                _draft_recipe(name="Grilled Salmon"),
                _draft_recipe(name="Oatmeal Bowl"),
            ]
        )
    )

    assert [r.source for r in result] == [RecipeSource.SYNTHESIZED, RecipeSource.CATALOGUE]
    assert result[1] is linked


def test_empty_draft_maps_to_empty_list() -> None:
    mapper = RecipeMapper(InMemoryRecipeCatalogue())

    assert mapper.map(RecommendationDraft()) == []
