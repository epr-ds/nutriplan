package com.nutriplan.shared.data.model

import kotlinx.serialization.Serializable

/**
 * A catalog recipe (`RecipeResponse` in `contracts/dietary.openapi.yaml`).
 *
 * [nutritionalInfo] is per serving. Times are in minutes. Optional fields the server may leave out
 * are nullable; the lists default to empty.
 */
@Serializable
data class Recipe(
    val id: String,
    val name: String,
    val description: String? = null,
    val ingredients: List<RecipeIngredient> = emptyList(),
    val instructions: List<String> = emptyList(),
    val prepTime: Int? = null,
    val cookTime: Int? = null,
    val servings: Int? = null,
    val imageUrl: String? = null,
    val nutritionalInfo: NutritionalInfo? = null,
    /** Any of `omnivore`, `vegetarian`, `vegan`, `keto`, `paleo`. */
    val dietaryTypes: List<String> = emptyList(),
)

/** One ingredient line of a recipe (`IngredientResponse`); a null value means unknown. */
@Serializable
data class RecipeIngredient(
    val name: String,
    val quantity: Double? = null,
    val unit: String? = null,
    val calories: Int? = null,
    val protein: Double? = null,
    val carbs: Double? = null,
    val fat: Double? = null,
    val sugar: Double? = null,
)

/**
 * Catalog-wide nutrition provenance and the medical disclaimer the UI must show
 * (`NutritionDisclaimerResponse`, `GET /nutrition/disclaimer`).
 */
@Serializable
data class NutritionDisclaimer(
    val disclaimer: String,
    /** Always false: the payload makes no medical or health claims. */
    val medicalAdvice: Boolean = false,
    val sources: List<NutritionSource> = emptyList(),
    val lastReviewed: String? = null,
)

/** A verified dataset the catalog's nutrition values are traceable to (`NutritionSource`). */
@Serializable
data class NutritionSource(
    val id: String,
    val name: String,
    val url: String,
    val verified: Boolean = false,
)

/**
 * Maps each nutrient field to the id of the verified source it comes from
 * (`NutritionFieldSources` in `contracts/dietary.openapi.yaml`; DPL-305).
 */
@Serializable
data class NutritionFieldSources(
    val calories: String,
    val protein: String,
    val carbs: String,
    val fat: String,
    val sugar: String,
)

/**
 * Query for `GET /recipes`. A recipe matches when it contains at least one of [ingredients]
 * (case-insensitive); results are ranked by how many match. [page] is 1-based.
 */
data class RecipeSearchQuery(
    val ingredients: List<String> = emptyList(),
    val dietType: String? = null,
    val maxCalories: Int? = null,
    val minProtein: Double? = null,
    val page: Int = 1,
    val limit: Int = 20,
)
