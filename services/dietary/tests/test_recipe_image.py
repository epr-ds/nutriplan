"""DPL-207: Recipe image pipeline — CDN imageUrl, placeholder fallback, validation."""

from app.api.schemas import RecipeResponse
from app.domain.recipe import (
    RECIPE_IMAGE_CDN_BASE_URL,
    RECIPE_IMAGE_PLACEHOLDER,
    Recipe,
    is_valid_recipe_image_url,
)

CDN_IMAGE_URL = "https://images.nutriplan.app/recipes/overnight-oats.jpg"


def _recipe(image_url: str | None = None) -> Recipe:
    return Recipe.create(name="Overnight Oats with Berries", servings=2, image_url=image_url)


def test_populated_recipe_image_is_served_via_cdn():
    recipe = _recipe(CDN_IMAGE_URL)

    assert recipe.effective_image_url == CDN_IMAGE_URL
    assert recipe.effective_image_url.startswith(RECIPE_IMAGE_CDN_BASE_URL)


def test_missing_recipe_image_falls_back_to_a_deterministic_placeholder():
    first = Recipe.create(name="Oatmeal", servings=1)
    second = Recipe.create(name="Oatmeal", servings=1)

    assert first.effective_image_url == second.effective_image_url
    assert first.effective_image_url == RECIPE_IMAGE_PLACEHOLDER


def test_invalid_or_oversized_recipe_image_falls_back_to_the_deterministic_placeholder():
    oversized = f"https://images.nutriplan.app/recipes/{'a' * 600}.jpg"

    # Image sizes are validated: an over-long reference is rejected, not served.
    assert len(oversized) > 512
    assert not is_valid_recipe_image_url(oversized)
    assert _recipe(oversized).effective_image_url == RECIPE_IMAGE_PLACEHOLDER
    assert _recipe("not-an-image-url").effective_image_url == RECIPE_IMAGE_PLACEHOLDER


def test_recipe_response_serves_the_effective_image_url():
    assert RecipeResponse.from_recipe(_recipe(CDN_IMAGE_URL)).image_url == CDN_IMAGE_URL
    assert RecipeResponse.from_recipe(_recipe(None)).image_url == RECIPE_IMAGE_PLACEHOLDER
