package com.nutriplan.shared.data.model

import kotlinx.serialization.Serializable

/** Request to analyze a meal. */
@Serializable
data class AnalyzeMealRequest(
    val mealDescription: String,
    val imageUrl: String? = null,
)

/** Response from meal analysis. */
@Serializable
data class AnalyzeMealResponse(
    val detectedFoods: List<DetectedFood>? = null,
    val nutritionEstimate: NutritionInfo? = null,
    val confidence: Double? = null,
)

/** A detected food item. */
@Serializable
data class DetectedFood(
    val name: String,
    val estimatedAmount: String? = null,
    val calories: Int? = null,
)

/** Request for AI recommendations. */
@Serializable
data class RecommendationsRequest(
    val dietaryPreferences: List<String>? = null,
    val calorieTarget: Int? = null,
    val mealType: String? = null,
    val excludeIngredients: List<String>? = null,
    val maxResults: Int? = null,
)

/** AI recommendation result. */
@Serializable
data class RecommendationResult(
    val recipeId: String,
    val recipeName: String,
    val reason: String? = null,
    val nutritionInfo: NutritionInfo? = null,
    val matchScore: Double? = null,
)

/** Request to optimize a meal plan. */
@Serializable
data class OptimizePlanRequest(
    val planId: String,
    val constraints: PlanConstraints? = null,
)

/** Constraints for plan optimization. */
@Serializable
data class PlanConstraints(
    val targetCalories: Int? = null,
    val dietaryPreferences: List<String>? = null,
    val maxMealsPerDay: Int? = null,
    val minVariety: Boolean? = null,
)

/** Response from plan optimization. */
@Serializable
data class OptimizePlanResponse(
    val planId: String,
    val optimizedMeals: List<OptimizedMeal>? = null,
    val changesSummary: String? = null,
    val estimatedCalorieChange: Int? = null,
)

/** An optimized meal suggestion. */
@Serializable
data class OptimizedMeal(
    val recipeId: String,
    val recipeName: String,
    val mealType: String,
    val scheduledDate: String,
    val reason: String? = null,
    val nutritionInfo: NutritionInfo? = null,
)
