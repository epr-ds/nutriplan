package com.nutriplan.shared.data.model

import kotlinx.serialization.Serializable

/** Macro nutrient targets. */
@Serializable
data class MacroTargets(
    val protein: Double? = null,
    val carbs: Double? = null,
    val fat: Double? = null,
)

/** Estimated nutrition from AI meal analysis. */
@Serializable
data class NutritionEstimate(
    val calories: Int,
    val protein: Double,
    val carbs: Double,
    val fat: Double,
    val sugar: Double,
)

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

/** AI recommendation request. */
@Serializable
data class AIRecommendationRequest(
    val context: String,
    val dietaryPreferences: DietaryPreferencesSchema?,
    val availableIngredients: List<String> = emptyList(),
    val mealType: String? = null,
    val calorieTarget: Int? = null,
    val previousMeals: List<String> = emptyList(),
    val constraints: List<String> = emptyList(),
    val language: String = "en",
)

/** Dietary preferences schema for AI recommendations. */
@Serializable
data class DietaryPreferencesSchema(
    val dietType: String? = null,
    val allergies: List<String> = emptyList(),
    val excludedIngredients: List<String> = emptyList(),
    val cuisinePreferences: List<String> = emptyList(),
    val dailyCalorieTarget: Int? = null,
    val macroTargets: MacroTargets? = null,
)

/** AI recommendation response. */
@Serializable
data class AIRecommendationResponse(
    val recommendations: List<RecommendedRecipe>,
    val reasoning: String,
    val nutritionalAlignment: NutritionalAlignment?,
    val disclaimer: String?,
)

/** A recommended recipe with context. */
@Serializable
data class RecommendedRecipe(
    val recipe: RecipeResponse,
    val reason: String,
    val mealType: String,
)

/** Nutritional alignment score. */
@Serializable
data class NutritionalAlignment(
    val score: Double,
    val proteinAlignment: Double,
    val carbsAlignment: Double,
    val fatAlignment: Double,
    val sugarAlignment: Double,
)

/** Single ingredient for meal analysis. */
@Serializable
data class MealIngredient(
    val name: String,
    val quantity: Double,
    val unit: String,
    val calories: Int?,
    val protein: Double?,
    val carbs: Double?,
    val fat: Double?,
    val sugar: Double?,
)

/** AI meal analysis response. */
@Serializable
data class NutritionalAnalysisResponse(
    val description: String,
    val estimatedNutrition: NutritionEstimate,
    val warnings: List<String> = emptyList(),
    val suggestions: List<String> = emptyList(),
    val confidence: Double,
)

