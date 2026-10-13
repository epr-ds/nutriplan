++ b/mobile/shared/src/commonMain/kotlin/com/nutriplan/shared/data/model/RecipeModels.kt
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

/** Recipe response from the Dietary service. */
@Serializable
data class RecipeResponse(
    val id: String,
    val name: String,
    val description: String,
    val servings: Int,
    val prepTimeMinutes: Int,
    val cookTimeMinutes: Int,
    val nutritionPerServing: NutritionPerServing,
    val ingredients: List<RecipeIngredient>,
    val instructions: List<String>,
    val tags: List<String>,
    val dietType: String?,
    val imageUrl: String?,
    val createdAt: String,
)

/** Nutrition per serving for a recipe. */
@Serializable
data class NutritionPerServing(
    val calories: Int,
    val protein: Double,
    val carbs: Double,
    val fat: Double,
    val sugar: Double,
)

/** Single ingredient in a recipe. */
@Serializable
data class RecipeIngredient(
    val name: String,
    val quantity: Double,
    val unit: String,
    val calories: Int?,
    val protein: Double?,
    val carbs: Double?,
    val fat: Double?,
)

/** Recipe search query parameters. */
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

/** AI meal analysis request. */
@Serializable
data class AnalyzeMealRequest(
    val description: String,
    val ingredients: List<MealIngredient> = emptyList(),
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

/** AI plan optimization request. */
@Serializable
data class OptimizePlanRequest(
    val planId: String,
    val goal: String? = null,
)
