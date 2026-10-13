package com.nutriplan.shared.data.local

import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.PlanMeal
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json

/**
 * Offline cache of meal plans backed by SQLDelight.
 *
 * Plans written locally are stored with `synced = false` until [markSynced] is called after
 * the server accepted them; plans fetched from the server are stored with `synced = true`.
 */
class MealPlanCache(private val database: NutriPlanDatabase) {

    private val queries = database.mealPlanQueries
    private val preferencesSerializer = ListSerializer(String.serializer())

    /** All cached plans, newest start date first, with their meals. */
    fun getPlans(): List<MealPlan> =
        queries.selectAllPlans(::toPlan).executeAsList().map { it.withMeals() }

    /** A single cached plan with its meals, or null if it is not cached. */
    fun getPlan(id: String): MealPlan? =
        queries.selectPlanById(id, ::toPlan).executeAsOneOrNull()?.withMeals()

    /** Plans with local changes that still have to be sent to the server. */
    fun getUnsyncedPlans(): List<MealPlan> =
        queries.selectUnsyncedPlans(::toPlan).executeAsList().map { it.withMeals() }

    /** Ids of plans that mirror the server (no pending local changes). */
    fun getSyncedPlanIds(): List<String> = queries.selectSyncedPlanIds().executeAsList()

    /** Insert or replace [plan] and all its meals atomically. */
    fun upsert(plan: MealPlan, synced: Boolean) {
        database.transaction {
            queries.deleteMealsForPlan(plan.id)
            queries.upsertPlan(
                id = plan.id,
                name = plan.name,
                description = plan.description,
                user_id = plan.userId,
                start_date = plan.startDate,
                end_date = plan.endDate,
                dietary_preferences = plan.dietaryPreferences?.let {
                    Json.encodeToString(preferencesSerializer, it)
                },
                target_calories = plan.targetCalories?.toLong(),
                status = plan.status,
                created_at = plan.createdAt,
                updated_at = plan.updatedAt,
                synced = synced,
            )
            plan.meals.orEmpty().forEach { meal ->
                queries.insertMeal(
                    id = meal.id,
                    plan_id = plan.id,
                    recipe_id = meal.recipeId,
                    recipe_name = meal.recipeName,
                    meal_type = meal.mealType,
                    scheduled_date = meal.scheduledDate,
                    portion_size = meal.portionSize,
                    calories = meal.calories?.toLong(),
                )
            }
        }
    }

    /** Mark a plan as accepted by the server. */
    fun markSynced(id: String) {
        queries.markPlanSynced(id)
    }

    /** Remove a plan and its meals. */
    fun delete(id: String) {
        database.transaction {
            queries.deleteMealsForPlan(id)
            queries.deletePlan(id)
        }
    }

    private fun MealPlan.withMeals(): MealPlan = copy(meals = mealsFor(id))

    private fun mealsFor(planId: String): List<PlanMeal> =
        queries.selectMealsForPlan(planId) { id, plan_id, recipe_id, recipe_name, meal_type,
            scheduled_date, portion_size, calories ->
            PlanMeal(
                id = id,
                planId = plan_id,
                recipeId = recipe_id,
                recipeName = recipe_name,
                mealType = meal_type,
                scheduledDate = scheduled_date,
                portionSize = portion_size,
                calories = calories?.toInt(),
            )
        }.executeAsList()

    @Suppress("LongParameterList", "UNUSED_PARAMETER")
    private fun toPlan(
        id: String,
        name: String,
        description: String?,
        userId: String,
        startDate: String,
        endDate: String,
        dietaryPreferences: String?,
        targetCalories: Long?,
        status: String,
        createdAt: String?,
        updatedAt: String?,
        synced: Boolean,
    ): MealPlan = MealPlan(
        id = id,
        name = name,
        description = description,
        userId = userId,
        startDate = startDate,
        endDate = endDate,
        dietaryPreferences = dietaryPreferences?.let { Json.decodeFromString(preferencesSerializer, it) },
        targetCalories = targetCalories?.toInt(),
        meals = null,
        status = status,
        createdAt = createdAt,
        updatedAt = updatedAt,
    )
}
