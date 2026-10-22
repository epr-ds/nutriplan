package com.nutriplan.shared.data.model

import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.Serializable
import kotlinx.serialization.Transient
import kotlin.math.roundToInt

/*
 * Meal plan models, aligned with contracts/dietary.openapi.yaml (the source of truth the Dietary
 * service implements and tests against). Field names, optionality and value casing follow the
 * contract: statuses and meal types are lowercase strings (`draft`, `breakfast`, ...), a plan's
 * calorie goal is `dailyCalorieTarget`, and a meal is placed on a day by `dayIndex`, not by a date.
 */

/** Body of `POST /meal-plans` (`CreateMealPlanRequest`). The server requires a daily calorie target. */
@Serializable
data class CreateMealPlanRequest(
    val name: String,
    /** ISO date (`yyyy-MM-dd`). */
    val startDate: String,
    /** ISO date (`yyyy-MM-dd`); must not be before [startDate]. */
    val endDate: String,
    val dailyCalorieTarget: Int,
    val macroTargets: DietaryMacroTargets? = null,
    /** One of `omnivore`, `vegetarian`, `vegan`, `keto`, `paleo`. */
    val dietaryType: String? = null,
)

/** Body of `PATCH /meal-plans/{planId}`: the only edit the API offers is a status transition. */
@Serializable
data class UpdateMealPlanStatusRequest(
    /** One of `active`, `completed`, `saved`. A plan can never go back to `draft`. */
    val status: String,
)

/** Body of `POST /meal-plans/{planId}/meals` (`AddMealRequest`). */
@Serializable
data class AddMealRequest(
    /** One of `breakfast`, `lunch`, `dinner`, `snack`. */
    val mealType: String,
    val recipeId: String,
    val servings: Double,
)

/**
 * Body of `PATCH /meal-plans/{planId}/meals/{mealId}` (`UpdateMealRequest`). The API needs at least
 * one field and treats an absent field as "leave unchanged", so unset fields are never sent (not
 * even as null).
 */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class UpdateMealRequest(
    @EncodeDefault(EncodeDefault.Mode.NEVER) val servings: Double? = null,
    /** 0-based day within the plan's inclusive date range. */
    @EncodeDefault(EncodeDefault.Mode.NEVER) val dayIndex: Int? = null,
    /** Post-meal rating 1 to 5. */
    @EncodeDefault(EncodeDefault.Mode.NEVER) val satisfactionLevel: Int? = null,
)

/** One row of `GET /meal-plans` (`MealPlanSummaryResponse`): enough to list a plan, nothing more. */
@Serializable
data class MealPlanSummary(
    val id: String,
    val name: String,
    val startDate: String,
    val endDate: String,
    /** `draft`, `active`, `completed` or `saved`. */
    val status: String,
)

/** A full meal plan (`MealPlanResponse`), as returned by create, get and status change. */
@Serializable
data class MealPlan(
    val id: String,
    val name: String,
    val startDate: String,
    val endDate: String,
    val dailyCalorieTarget: Int,
    /** `draft`, `active`, `completed` or `saved`. */
    val status: String,
    val meals: List<PlanMeal> = emptyList(),
    val nutritionalSummary: NutritionalSummary? = null,
)

/**
 * A planned meal (`MealResponse`).
 *
 * Plan reads do not expand the recipe: [recipe] is only present on the add-meal response, and a
 * meal carries no recipe id. A meal is placed on a day by [dayIndex] (0-based within the plan's
 * inclusive date range), or has none yet.
 */
@Serializable
data class PlanMeal(
    val id: String,
    /** `breakfast`, `lunch`, `dinner` or `snack`. */
    val mealType: String,
    val servings: Double,
    val dayIndex: Int? = null,
    /** Post-meal rating 1 to 5, or null when unrated. */
    val satisfactionLevel: Int? = null,
    val recipe: PlanMealRecipe? = null,
    val nutritionalInfo: NutritionalInfo? = null,
    /**
     * An edit of this meal is shown but has not reached the server yet (DPL-407). Local only: it is
     * never sent or read, so it is not part of the API model.
     */
    @Transient val syncPending: Boolean = false,
)

/** The part of a recipe the plan screens need; the full `RecipeResponse` has much more. */
@Serializable
data class PlanMealRecipe(
    val id: String,
    val name: String,
    val imageUrl: String? = null,
)

/** A bundle of nutrient values (`NutritionalInfo`); null means unknown, which is not the same as 0. */
@Serializable
data class NutritionalInfo(
    val calories: Int? = null,
    val protein: Double? = null,
    val carbs: Double? = null,
    val fat: Double? = null,
    val sugar: Double? = null,
)

/** These values times [factor] (calories rounded), for example for a different number of servings. */
fun NutritionalInfo.scaledBy(factor: Double) = NutritionalInfo(
    calories = calories?.let { (it * factor).roundToInt() },
    protein = protein?.let { it * factor },
    carbs = carbs?.let { it * factor },
    fat = fat?.let { it * factor },
    sugar = sugar?.let { it * factor },
)

/** Totals, daily averages and targets-vs-progress for a plan (`NutritionalSummary`). */
@Serializable
data class NutritionalSummary(
    val total: NutritionalInfo? = null,
    val dailyAverage: NutritionalInfo? = null,
    val targets: NutritionalTargets = NutritionalTargets(),
    val progress: NutritionalProgress = NutritionalProgress(),
)

/** A plan's daily goals (`NutritionalTargets`); a null macro means no target was set. */
@Serializable
data class NutritionalTargets(
    val calories: Int? = null,
    val protein: Int? = null,
    val carbs: Int? = null,
    val fat: Int? = null,
    val sugar: Int? = null,
)

/** Per-nutrient progress of the daily average against its target (`NutritionalProgress`). */
@Serializable
data class NutritionalProgress(
    val calories: NutrientProgress = NutrientProgress(),
    val protein: NutrientProgress = NutrientProgress(),
    val carbs: NutrientProgress = NutrientProgress(),
    val fat: NutrientProgress = NutrientProgress(),
    val sugar: NutrientProgress = NutrientProgress(),
)

/** One nutrient's daily average measured against its target (`NutrientProgress`). */
@Serializable
data class NutrientProgress(
    val target: Double? = null,
    val actual: Double? = null,
    val percentOfTarget: Double? = null,
    /** `under`, `on_target` or `over`; null when it cannot be judged. */
    val status: String? = null,
)

/** Query parameters for `GET /meal-plans` (1-based [page]; the server defaults to 20 per page). */
data class MealPlanQuery(
    /** `active`, `completed` or `saved`; omit for all plans. */
    val status: String? = null,
    val page: Int? = null,
    val limit: Int? = null,
)

/**
 * Nutrition values as the AI models use them (see `AiModels.kt`). Recipes and meals use
 * [NutritionalInfo], which follows the Dietary contract.
 */
@Serializable
data class NutritionInfo(
    val calories: Int? = null,
    val protein: Double? = null,
    val carbohydrates: Double? = null,
    val fat: Double? = null,
    val fiber: Double? = null,
)
