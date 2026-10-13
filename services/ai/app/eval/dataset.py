"""The fixed eval set: representative prompts with known constraints (AIA-701).

This is the "fixed prompt set" AIA-701 grades. Each :class:`~app.eval.case.EvalCase` pins a
realistic recommendation scenario, the constraints it must respect (on the command), and a recorded
set of model recipes to score. The set is deliberately a *mixed* baseline -- mostly
constraint-respecting and well-aligned, with a few deliberate misses and two hard-constraint leaks
-- so the two metrics are non-trivial and a regression (a new leak, or drifting alignment) moves
them measurably.

Constraint matching here is the scorer's hard-preference gate, which is **exact**: a diet is
respected when the recipe lists it, and an excluded ingredient leaks only when it appears as an
ingredient name verbatim. Recipes are therefore written with that precise vocabulary.
"""

from __future__ import annotations

from app.eval.case import EvalCase
from app.recommendations.commands import (
    MacroTargets,
    RecommendationCommand,
    RecommendationContext,
)
from app.recommendations.recipes import (
    RecipeSource,
    RecommendedIngredient,
    RecommendedNutrition,
    RecommendedRecipe,
)


def _recipe(
    name: str,
    *,
    calories: int,
    protein: int | None = None,
    carbs: int | None = None,
    fat: int | None = None,
    sugar: int | None = None,
    diets: tuple[str, ...] = (),
    ingredients: tuple[str, ...] = (),
) -> RecommendedRecipe:
    return RecommendedRecipe(
        id=name.casefold().replace(" ", "-"),
        name=name,
        servings=1,
        ingredients=tuple(RecommendedIngredient(name=item) for item in ingredients),
        instructions=("Prepare and serve.",),
        nutrition=RecommendedNutrition(
            calories=calories, protein=protein, carbs=carbs, fat=fat, sugar=sugar
        ),
        source=RecipeSource.SYNTHESIZED,
        dietary_types=diets,
    )


def _command(
    *,
    diet_type: str | None = None,
    allergies: tuple[str, ...] = (),
    excluded_ingredients: tuple[str, ...] = (),
    calorie_target: int | None = None,
    macro_targets: MacroTargets | None = None,
) -> RecommendationCommand:
    return RecommendationCommand(
        context=RecommendationContext.MEAL_PLAN,
        diet_type=diet_type,
        allergies=allergies,
        excluded_ingredients=excluded_ingredients,
        calorie_target=calorie_target,
        macro_targets=macro_targets,
    )


EVAL_SET: tuple[EvalCase, ...] = (
    EvalCase(
        name="vegan-weeknight-dinner",
        prompt="Vegan weeknight dinners around 500 kcal.",
        command=_command(diet_type="vegan", calorie_target=500),
        recipes=(
            _recipe("Chickpea Stew", calories=500, protein=24, diets=("vegan",)),
            _recipe("Tofu Stir-Fry", calories=520, protein=28, diets=("vegan",)),
            _recipe("Lentil Curry", calories=480, protein=22, diets=("vegan",)),
        ),
    ),
    EvalCase(
        name="peanut-allergy-snacks",
        prompt="Nut-free snacks near 300 kcal for a peanut allergy.",
        command=_command(allergies=("peanuts",), calorie_target=300),
        recipes=(
            _recipe("Apple and Oats", calories=300, ingredients=("apple", "oats")),
            _recipe("Rice Cake Stack", calories=290, ingredients=("rice cake", "banana")),
        ),
    ),
    EvalCase(
        name="high-protein-lunch",
        prompt="High-protein lunches: 40 g protein, about 600 kcal.",
        command=_command(macro_targets=MacroTargets(protein_grams=40), calorie_target=600),
        recipes=(
            _recipe("Grilled Chicken Bowl", calories=600, protein=42),
            _recipe("Salmon Plate", calories=620, protein=40),
        ),
    ),
    EvalCase(
        name="macro-miss-breakfast",
        prompt="High-protein breakfasts: 35 g protein, about 450 kcal.",
        command=_command(macro_targets=MacroTargets(protein_grams=35), calorie_target=450),
        recipes=(
            _recipe("Pancake Stack", calories=450, protein=8),
            _recipe("Fruit Bowl", calories=440, protein=6),
        ),
    ),
    EvalCase(
        name="calorie-control-dinner",
        prompt="Light dinners around 550 kcal.",
        command=_command(calorie_target=550),
        recipes=(
            _recipe("Veggie Pasta", calories=560),
            _recipe("Loaded Burrito", calories=900),
        ),
    ),
    EvalCase(
        name="vegan-with-dairy-leak",
        prompt="Vegan lunches around 500 kcal (one recorded output is not vegan).",
        command=_command(diet_type="vegan", calorie_target=500),
        recipes=(
            _recipe("Bean Tacos", calories=500, protein=20, diets=("vegan",)),
            _recipe("Cheese Quesadilla", calories=510, protein=22, diets=("vegetarian",)),
        ),
    ),
    EvalCase(
        name="peanut-allergy-with-leak",
        prompt="Nut-free trail snacks near 300 kcal (one recorded output leaks peanuts).",
        command=_command(allergies=("peanuts",), calorie_target=300),
        recipes=(
            _recipe("Seed Bar", calories=300, ingredients=("sunflower seeds", "oats")),
            _recipe("Trail Mix", calories=310, ingredients=("peanuts", "raisins")),
        ),
    ),
)
"""The fixed, version-controlled eval set graded by ``python -m app.eval``."""
