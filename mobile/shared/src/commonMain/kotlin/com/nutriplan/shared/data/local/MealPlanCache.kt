package com.nutriplan.shared.data.local

import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.NutritionalSummary
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.PlanMealRecipe
import kotlinx.serialization.json.Json

/**
 * On-device read cache of meal plans, so the app can show what it last received when the server
 * cannot be reached.
 *
 * The list endpoint only returns summaries, so a plan is cached in two levels: a summary (from the
 * list) and, once the plan has been opened, its detail (target, meals, nutrition). [getPlan] returns
 * only plans whose detail was cached.
 */
class MealPlanCache(private val database: NutriPlanDatabase) {

    private val queries = database.mealPlanQueries

    /** Tolerant on read: a cached blob written by an older app version must never crash the app. */
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /** All cached plan summaries, newest start date first. */
    fun getPlans(): List<MealPlanSummary> =
        queries.selectAllPlans { id, name, startDate, endDate, status ->
            MealPlanSummary(id = id, name = name, startDate = startDate, endDate = endDate, status = status)
        }.executeAsList()

    /** A plan with its meals, or null if it is not cached or only its summary is. */
    fun getPlan(id: String): MealPlan? =
        queries.selectDetailedPlanById(id) { planId, name, startDate, endDate, status, calorieTarget, summaryJson, _ ->
            MealPlan(
                id = planId,
                name = name,
                startDate = startDate,
                endDate = endDate,
                // Always set together with has_detail = 1 (upsertDetail), which this query requires.
                dailyCalorieTarget = (calorieTarget ?: 0L).toInt(),
                status = status,
                meals = mealsFor(planId),
                nutritionalSummary = summaryJson.decodeOrNull<NutritionalSummary>(),
            )
        }.executeAsOneOrNull()

    /** Ids of every cached plan. */
    fun getPlanIds(): List<String> = queries.selectPlanIds().executeAsList()

    /** Insert or refresh summaries, leaving any cached detail of the same plans in place. */
    fun upsertSummaries(plans: List<MealPlanSummary>) {
        database.transaction {
            plans.forEach { plan ->
                queries.updateSummary(
                    name = plan.name,
                    start_date = plan.startDate,
                    end_date = plan.endDate,
                    status = plan.status,
                    id = plan.id,
                )
                queries.insertSummaryIfMissing(
                    id = plan.id,
                    name = plan.name,
                    start_date = plan.startDate,
                    end_date = plan.endDate,
                    status = plan.status,
                )
            }
        }
    }

    /** Insert or replace a full [plan] and all its meals atomically. */
    fun upsertPlan(plan: MealPlan) {
        database.transaction {
            queries.deleteMealsForPlan(plan.id)
            queries.upsertDetail(
                id = plan.id,
                name = plan.name,
                start_date = plan.startDate,
                end_date = plan.endDate,
                status = plan.status,
                daily_calorie_target = plan.dailyCalorieTarget.toLong(),
                nutritional_summary = plan.nutritionalSummary?.let { json.encodeToString(NutritionalSummary.serializer(), it) },
            )
            plan.meals.forEachIndexed { position, meal ->
                queries.insertMeal(
                    id = meal.id,
                    plan_id = plan.id,
                    position = position.toLong(),
                    meal_type = meal.mealType,
                    servings = meal.servings,
                    day_index = meal.dayIndex?.toLong(),
                    satisfaction_level = meal.satisfactionLevel?.toLong(),
                    recipe = meal.recipe?.let { json.encodeToString(PlanMealRecipe.serializer(), it) },
                    nutritional_info = meal.nutritionalInfo?.let { json.encodeToString(NutritionalInfo.serializer(), it) },
                )
            }
        }
    }

    /** Forget a plan's cached meals and detail, keeping its summary (its detail is stale). */
    fun invalidateDetail(id: String) {
        database.transaction {
            queries.deleteMealsForPlan(id)
            queries.invalidateDetail(id)
        }
    }

    /** Remove a plan entirely. */
    fun delete(id: String) {
        database.transaction {
            queries.deleteMealsForPlan(id)
            queries.deletePlan(id)
        }
    }

    /** Remove every cached plan and meal (for example on logout). */
    fun clear() {
        database.transaction {
            queries.deleteAllMeals()
            queries.deleteAllPlans()
        }
    }

    private fun mealsFor(planId: String): List<PlanMeal> =
        queries.selectMealsForPlan(planId) {
            id, _, _, mealType, servings, dayIndex, satisfactionLevel, recipeJson, nutritionJson ->
            PlanMeal(
                id = id,
                mealType = mealType,
                servings = servings,
                dayIndex = dayIndex?.toInt(),
                satisfactionLevel = satisfactionLevel?.toInt(),
                recipe = recipeJson.decodeOrNull<PlanMealRecipe>(),
                nutritionalInfo = nutritionJson.decodeOrNull<NutritionalInfo>(),
            )
        }.executeAsList()

    private inline fun <reified T> String?.decodeOrNull(): T? =
        this?.let { runCatching { json.decodeFromString<T>(it) }.getOrNull() }
}
