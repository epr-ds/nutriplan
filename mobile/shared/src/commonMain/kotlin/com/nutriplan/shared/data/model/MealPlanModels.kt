package com.nutriplan.shared.data.model

import kotlinx.serialization.Serializable

/** Request body for creating a meal plan. */
@Serializable
data class CreateMealPlanRequest(
    val name: String,
    val description: String? = null,
    val startDate: String,
    val endDate: String,
    val dietaryPreferences: List<String>? = null,
    val targetCalories: Int? = null,
)

/** Request body for updating a meal plan. */
@Serializable
data class UpdateMealPlanRequest(
    val name: String? = null,
    val description: String? = null,
    val startDate: String? = null,
    val endDate: String? = null,
    val dietaryPreferences: List<String>? = null,
    val targetCalories: Int? = null,
)

/** Request body for adding a meal to a plan. */
@Serializable
data class AddMealRequest(
    val recipeId: String,
    val mealType: String,
    val scheduledDate: String,
    val portionSize: Double? = null,
)

/** A meal plan entity. */
@Serializable
data class MealPlan(
    val id: String,
    val name: String,
    val description: String? = null,
    val userId: String,
    val startDate: String,
    val endDate: String,
    val dietaryPreferences: List<String>? = null,
    val targetCalories: Int? = null,
    val meals: List<PlanMeal>? = null,
    val status: String,
    val createdAt: String? = null,
    val updatedAt: String? = null,
)

/** A meal within a plan. */
@Serializable
data class PlanMeal(
    val id: String,
    val planId: String,
    val recipeId: String,
    val recipeName: String,
    val mealType: String,
    val scheduledDate: String,
    val portionSize: Double? = null,
    val calories: Int? = null,
)

/** Query parameters for listing meal plans. */
data class MealPlanQuery(
    val status: String? = null,
    val limit: Int? = null,
    val offset: Int? = null,
)

/** Query parameters for listing recipes. */
data class RecipeQuery(
    val dietaryPreference: String? = null,
    val calorieRangeMin: Int? = null,
    val calorieRangeMax: Int? = null,
    val limit: Int? = null,
    val offset: Int? = null,
)

/** A recipe entity. */
@Serializable
data class Recipe(
    val id: String,
    val name: String,
    val description: String? = null,
    val ingredients: List<Ingredient>? = null,
    val nutritionInfo: NutritionInfo? = null,
    val dietaryTags: List<String>? = null,
    val imageUrl: String? = null,
    val prepTimeMinutes: Int? = null,
    val servings: Int? = null,
)

/** Nutrition information for a recipe. */
@Serializable
data class NutritionInfo(
    val calories: Int? = null,
    val protein: Double? = null,
    val carbohydrates: Double? = null,
    val fat: Double? = null,
    val fiber: Double? = null,
)

/** Ingredient for a recipe. */
@Serializable
data class Ingredient(
    val name: String,
    val amount: Double? = null,
    val unit: String? = null,
)
