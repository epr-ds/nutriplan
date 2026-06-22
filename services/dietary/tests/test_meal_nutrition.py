"""DPL-301: per-meal nutrition computation (``compute_meal_nutrition``).

Pure, Mongo-free tests for the domain service that derives a planned meal's nutrition from the
recipe it references, scaled to the meal's servings. They pin down the source-of-truth precedence
(authored per-serving ``nutritionalInfo`` over an ingredient breakdown), the ``Sum(ingredients) /
servings`` derivation, the **half-up** rounding rule (calories to a whole number, macros to one
decimal place) and the "unknown stays ``None``" rule.
"""

from app.domain.nutrition import compute_meal_nutrition
from app.domain.recipe import Ingredient, NutritionalInfo, Recipe

_OATS_INGREDIENTS = [
    Ingredient(name="Rolled oats", calories=300, protein=10.5, carbs=54.0, fat=5.0, sugar=1.2),
    Ingredient(name="Milk", calories=100, protein=7.0, carbs=10.0, fat=4.0, sugar=10.0),
    Ingredient(name="Chia seeds", calories=50, protein=1.7, carbs=4.2, fat=3.1, sugar=0.0),
    Ingredient(name="Mixed berries", calories=35, protein=0.5, carbs=8.0, fat=0.2, sugar=6.0),
]


def _recipe(*, servings=2, nutritional_info=None, ingredients=None) -> Recipe:
    return Recipe.create(
        name="Test Recipe",
        servings=servings,
        ingredients=ingredients or [],
        nutritional_info=nutritional_info,
    )


def test_scales_authored_per_serving_nutrition_by_meal_servings():
    recipe = _recipe(
        nutritional_info=NutritionalInfo(
            calories=400, protein=30.0, carbs=40.0, fat=10.0, sugar=5.0
        )
    )

    info = compute_meal_nutrition(recipe, servings=2)

    assert info.calories == 800
    assert info.protein == 60.0
    assert info.carbs == 80.0
    assert info.fat == 20.0
    assert info.sugar == 10.0


def test_single_serving_returns_per_serving_values_unchanged():
    recipe = _recipe(
        nutritional_info=NutritionalInfo(calories=243, protein=9.9, carbs=38.1, fat=6.2, sugar=8.6)
    )

    info = compute_meal_nutrition(recipe, servings=1)

    assert info.calories == 243
    assert info.protein == 9.9
    assert info.carbs == 38.1
    assert info.fat == 6.2
    assert info.sugar == 8.6


def test_rounds_calories_half_up_to_whole_number():
    # 243 * 1.5 = 364.5 -> 365 (half-up; banker's rounding would give 364).
    recipe = _recipe(nutritional_info=NutritionalInfo(calories=243))

    info = compute_meal_nutrition(recipe, servings=1.5)

    assert info.calories == 365


def test_rounds_macros_half_up_to_one_decimal_place():
    # protein 9.9 * 1.5 = 14.85 -> 14.9 (half-up; banker's rounding would give 14.8).
    recipe = _recipe(nutritional_info=NutritionalInfo(protein=9.9, carbs=38.1, fat=6.2, sugar=8.6))

    info = compute_meal_nutrition(recipe, servings=1.5)

    assert info.protein == 14.9
    assert info.carbs == 57.2  # 38.1 * 1.5 = 57.15 -> 57.2
    assert info.fat == 9.3  # 6.2 * 1.5 = 9.30
    assert info.sugar == 12.9  # 8.6 * 1.5 = 12.9


def test_derives_from_ingredients_when_no_authored_nutrition():
    # Sum(ingredients) / recipe.servings, then * meal servings. Sums: 485 cal and 19.7 / 76.2 /
    # 12.3 / 17.2 g over 2 servings -> per-serving figures (242.5->243, 9.85->9.9, 6.15->6.2).
    recipe = _recipe(servings=2, ingredients=_OATS_INGREDIENTS)

    info = compute_meal_nutrition(recipe, servings=1)

    assert info.calories == 243
    assert info.protein == 9.9
    assert info.carbs == 38.1
    assert info.fat == 6.2
    assert info.sugar == 8.6


def test_ingredient_derivation_scales_with_meal_servings():
    recipe = _recipe(servings=2, ingredients=_OATS_INGREDIENTS)

    info = compute_meal_nutrition(recipe, servings=2)

    assert info.calories == 485  # (485 / 2) * 2
    assert info.protein == 19.7
    assert info.carbs == 76.2


def test_authored_nutrition_is_preferred_over_ingredients():
    # Authored per-serving (250) wins over the ingredient-derived figure (485 / 2 = 243).
    recipe = _recipe(
        servings=2,
        ingredients=_OATS_INGREDIENTS,
        nutritional_info=NutritionalInfo(calories=250),
    )

    info = compute_meal_nutrition(recipe, servings=1)

    assert info.calories == 250


def test_unknown_macros_stay_none_not_zero():
    recipe = _recipe(nutritional_info=NutritionalInfo(calories=400, protein=30.0))

    info = compute_meal_nutrition(recipe, servings=2)

    assert info.calories == 800
    assert info.protein == 60.0
    assert info.carbs is None
    assert info.fat is None
    assert info.sugar is None


def test_ingredient_macro_is_none_when_no_ingredient_reports_it():
    # Every ingredient reports calories but none reports sugar -> sugar stays unknown.
    ingredients = [
        Ingredient(name="A", calories=100, protein=5.0),
        Ingredient(name="B", calories=200, protein=10.0),
    ]
    recipe = _recipe(servings=1, ingredients=ingredients)

    info = compute_meal_nutrition(recipe, servings=1)

    assert info.calories == 300
    assert info.protein == 15.0
    assert info.carbs is None
    assert info.fat is None
    assert info.sugar is None


def test_recipe_without_any_nutrition_yields_all_none():
    recipe = _recipe(servings=1, ingredients=[Ingredient(name="Water")])

    info = compute_meal_nutrition(recipe, servings=3)

    assert info.calories is None
    assert info.protein is None
    assert info.carbs is None
    assert info.fat is None
    assert info.sugar is None


def test_partial_ingredient_data_treats_missing_as_zero_within_a_known_field():
    # Field is known overall (one ingredient reports it) so the other ingredient counts as 0.
    ingredients = [
        Ingredient(name="A", calories=100, protein=8.0),
        Ingredient(name="B", calories=100),  # no protein
    ]
    recipe = _recipe(servings=1, ingredients=ingredients)

    info = compute_meal_nutrition(recipe, servings=1)

    assert info.calories == 200
    assert info.protein == 8.0
