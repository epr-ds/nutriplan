"""Reference recipe catalog + idempotent seeding (DPL-201).

The dietary domain needs a baseline set of recipes that meal plans can reference before any
authoring UI exists (DPL-105 validates ``recipeId`` against this catalog). The recipes below use
**stable ids and a fixed timestamp** so that ``seed_recipes`` is a pure upsert — re-running it on
every boot produces byte-identical documents and never churns existing data.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pymongo.collection import Collection

from app.domain.dietary_types import DietaryType
from app.domain.recipe import Ingredient, NutritionalInfo, Recipe

_SEED_TIMESTAMP = datetime(2024, 1, 1, tzinfo=UTC)


def _recipe(
    recipe_id: str,
    name: str,
    description: str,
    ingredients: list[Ingredient],
    instructions: list[str],
    prep_time: int,
    cook_time: int,
    servings: int,
    image_url: str,
    nutritional_info: NutritionalInfo,
    dietary_types: list[DietaryType],
) -> Recipe:
    return Recipe(
        id=recipe_id,
        name=name,
        description=description,
        ingredients=ingredients,
        instructions=instructions,
        prep_time=prep_time,
        cook_time=cook_time,
        servings=servings,
        image_url=image_url,
        nutritional_info=nutritional_info,
        dietary_types=dietary_types,
        created_at=_SEED_TIMESTAMP,
        updated_at=_SEED_TIMESTAMP,
    )


SEED_RECIPES: list[Recipe] = [
    _recipe(
        "11111111-1111-1111-1111-111111111111",
        "Overnight Oats with Berries",
        "No-cook oats soaked overnight with milk, chia and mixed berries.",
        [
            Ingredient(
                name="Rolled oats",
                quantity=80.0,
                unit="g",
                calories=300,
                protein=10.5,
                carbs=54.0,
                fat=5.0,
                sugar=1.2,
            ),
            Ingredient(
                name="Milk",
                quantity=200.0,
                unit="ml",
                calories=100,
                protein=7.0,
                carbs=10.0,
                fat=4.0,
                sugar=10.0,
            ),
            Ingredient(
                name="Chia seeds",
                quantity=10.0,
                unit="g",
                calories=50,
                protein=1.7,
                carbs=4.2,
                fat=3.1,
                sugar=0.0,
            ),
            Ingredient(
                name="Mixed berries",
                quantity=60.0,
                unit="g",
                calories=35,
                protein=0.5,
                carbs=8.0,
                fat=0.2,
                sugar=6.0,
            ),
        ],
        ["Combine oats, milk and chia in a jar.", "Top with berries.", "Refrigerate overnight."],
        5,
        0,
        2,
        "https://images.nutriplan.app/recipes/overnight-oats.jpg",
        NutritionalInfo(calories=243, protein=9.9, carbs=38.1, fat=6.2, sugar=8.6),
        [DietaryType.VEGETARIAN, DietaryType.OMNIVORE],
    ),
    _recipe(
        "22222222-2222-2222-2222-222222222222",
        "Grilled Chicken Quinoa Bowl",
        "Lean grilled chicken over fluffy quinoa with roasted vegetables.",
        [
            Ingredient(
                name="Chicken breast",
                quantity=300.0,
                unit="g",
                calories=495,
                protein=93.0,
                carbs=0.0,
                fat=11.0,
                sugar=0.0,
            ),
            Ingredient(
                name="Quinoa",
                quantity=120.0,
                unit="g",
                calories=440,
                protein=16.0,
                carbs=78.0,
                fat=7.0,
                sugar=0.0,
            ),
            Ingredient(
                name="Bell pepper",
                quantity=100.0,
                unit="g",
                calories=31,
                protein=1.0,
                carbs=6.0,
                fat=0.3,
                sugar=4.2,
            ),
            Ingredient(
                name="Olive oil",
                quantity=15.0,
                unit="ml",
                calories=133,
                protein=0.0,
                carbs=0.0,
                fat=15.0,
                sugar=0.0,
            ),
        ],
        [
            "Cook quinoa per package.",
            "Grill seasoned chicken.",
            "Roast peppers in olive oil.",
            "Assemble bowls.",
        ],
        15,
        20,
        2,
        "https://images.nutriplan.app/recipes/chicken-quinoa-bowl.jpg",
        NutritionalInfo(calories=550, protein=55.0, carbs=42.0, fat=16.6, sugar=2.1),
        [DietaryType.OMNIVORE],
    ),
    _recipe(
        "33333333-3333-3333-3333-333333333333",
        "Veggie Stir-Fry with Tofu",
        "Crispy tofu and seasonal vegetables in a light soy-ginger sauce.",
        [
            Ingredient(
                name="Firm tofu",
                quantity=250.0,
                unit="g",
                calories=360,
                protein=40.0,
                carbs=9.0,
                fat=20.0,
                sugar=2.0,
            ),
            Ingredient(
                name="Broccoli",
                quantity=150.0,
                unit="g",
                calories=51,
                protein=4.2,
                carbs=10.0,
                fat=0.6,
                sugar=2.5,
            ),
            Ingredient(
                name="Carrot",
                quantity=80.0,
                unit="g",
                calories=33,
                protein=0.7,
                carbs=8.0,
                fat=0.2,
                sugar=3.8,
            ),
            Ingredient(
                name="Soy sauce",
                quantity=20.0,
                unit="ml",
                calories=11,
                protein=2.0,
                carbs=1.0,
                fat=0.0,
                sugar=0.4,
            ),
        ],
        [
            "Press and cube tofu, then pan-fry until golden.",
            "Stir-fry vegetables.",
            "Add soy-ginger sauce and toss.",
        ],
        15,
        15,
        2,
        "https://images.nutriplan.app/recipes/tofu-stir-fry.jpg",
        NutritionalInfo(calories=228, protein=23.5, carbs=14.0, fat=10.4, sugar=4.4),
        [DietaryType.VEGAN, DietaryType.VEGETARIAN, DietaryType.OMNIVORE],
    ),
    _recipe(
        "44444444-4444-4444-4444-444444444444",
        "Baked Salmon with Roasted Vegetables",
        "Omega-rich salmon fillet baked with a medley of roasted vegetables.",
        [
            Ingredient(
                name="Salmon fillet",
                quantity=300.0,
                unit="g",
                calories=620,
                protein=60.0,
                carbs=0.0,
                fat=42.0,
                sugar=0.0,
            ),
            Ingredient(
                name="Sweet potato",
                quantity=200.0,
                unit="g",
                calories=172,
                protein=3.2,
                carbs=40.0,
                fat=0.2,
                sugar=8.4,
            ),
            Ingredient(
                name="Zucchini",
                quantity=120.0,
                unit="g",
                calories=20,
                protein=1.4,
                carbs=4.0,
                fat=0.4,
                sugar=3.0,
            ),
            Ingredient(
                name="Olive oil",
                quantity=15.0,
                unit="ml",
                calories=133,
                protein=0.0,
                carbs=0.0,
                fat=15.0,
                sugar=0.0,
            ),
        ],
        [
            "Heat oven to 200C.",
            "Toss vegetables in olive oil and roast 20 min.",
            "Add salmon and bake 12 min.",
        ],
        10,
        32,
        2,
        "https://images.nutriplan.app/recipes/baked-salmon.jpg",
        NutritionalInfo(calories=473, protein=32.3, carbs=22.0, fat=28.8, sugar=5.7),
        [DietaryType.PALEO, DietaryType.OMNIVORE],
    ),
]


def seed_recipes(collection: Collection) -> int:
    """Upsert the reference catalog into *collection*; return the number of seeded recipes.

    Idempotent: each recipe is matched by ``_id`` and fully replaced, so missing seeds are
    inserted and existing ones are refreshed without creating duplicates.
    """
    for recipe in SEED_RECIPES:
        doc = recipe.to_document()
        collection.replace_one({"_id": doc["_id"]}, doc, upsert=True)
    return len(SEED_RECIPES)
