@file:OptIn(ExperimentalSerializationApi::class)

package com.nutriplan.shared.data.model

import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.Serializable

/*
 * AI Advisor models (AIA-601), aligned with contracts/ai.openapi.yaml, the source of truth the AI
 * service is verified against. Optional request fields the user did not set are left out of the JSON
 * altogether (never sent as null), and responses reuse the recipe, meal plan and nutrition models
 * where the contract reuses their shapes.
 */

/** Body of `POST /ai/recommendations` (`AIRecommendationRequest`). */
@Serializable
data class AiRecommendationRequest(
    /** `meal_plan`, `single_meal` or `ingredient_based`. */
    val context: String,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val dietaryPreferences: AiDietaryPreferences? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val availableIngredients: List<String>? = null,
    /** `breakfast`, `lunch`, `dinner` or `snack`. */
    @EncodeDefault(EncodeDefault.Mode.NEVER) val mealType: String? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val calorieTarget: Int? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val previousMeals: List<String>? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val constraints: List<String>? = null,
    /** `es` or `en`: the language of the reasoning and disclaimer. */
    val language: String = "es",
)

/**
 * The caller's dietary preferences as the AI service reads them (`DietaryPreferencesRequest` in the
 * AI contract): the Identity preferences without the appetite rating, which the AI service does not
 * take.
 */
@Serializable
data class AiDietaryPreferences(
    @EncodeDefault(EncodeDefault.Mode.NEVER) val dietType: String? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val allergies: List<String>? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val dailyCalorieTarget: Int? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val macroTargets: DietaryMacroTargets? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val excludedIngredients: List<String>? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val cuisinePreferences: List<String>? = null,
)

/** Response of `POST /ai/recommendations` (`AIRecommendationResponse`). */
@Serializable
data class AiRecommendations(
    val recommendations: List<Recipe> = emptyList(),
    val reasoning: String? = null,
    val nutritionalAlignment: NutritionalAlignment? = null,
    /** The medical disclaimer every AI response carries (AIA-505); the UI must show it. */
    val disclaimer: String? = null,
)

/** How well a recommendation or meal fits the caller's targets: a 0-100 score and an explanation. */
@Serializable
data class NutritionalAlignment(
    val score: Double? = null,
    val details: String? = null,
)

/** Body of `POST /ai/analyze-meal` (`AnalyzeMealRequest`). */
@Serializable
data class AnalyzeMealRequest(
    /** Free-text description of the meal. */
    val description: String,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val ingredients: List<RecipeIngredient>? = null,
)

/** Response of `POST /ai/analyze-meal` (`NutritionalAnalysisResponse`). */
@Serializable
data class MealAnalysis(
    val nutritionalInfo: NutritionalInfo? = null,
    val alignment: NutritionalAlignment? = null,
    val warnings: List<String> = emptyList(),
    /** The medical disclaimer every AI response carries (AIA-505); the UI must show it. */
    val disclaimer: String? = null,
)

/**
 * Body of `POST /ai/optimize-plan` (`OptimizePlanRequest`). The response is the optimized plan as a
 * reviewable draft ([MealPlan]); the stored original is left untouched.
 */
@Serializable
data class OptimizePlanRequest(
    val planId: String,
    /** `balance_macros`, `increase_protein`, `reduce_calories` or `increase_satisfaction`. */
    @EncodeDefault(EncodeDefault.Mode.NEVER) val goal: String? = null,
)
