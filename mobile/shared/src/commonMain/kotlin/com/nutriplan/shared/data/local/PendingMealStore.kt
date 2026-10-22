package com.nutriplan.shared.data.local

import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.PlanMealRecipe
import kotlinx.serialization.json.Json

/** The id prefix of a meal that is only on this device so far (see [PendingMeal.tempMealId]). */
const val PENDING_MEAL_ID_PREFIX = "pending-"

/** Whether this meal is a stand-in for one that has not reached the server yet. */
val PlanMeal.isPending: Boolean get() = id.startsWith(PENDING_MEAL_ID_PREFIX)

/** Whether the plan shows something about this meal that the server does not know yet. */
val PlanMeal.isWaitingToSync: Boolean get() = isPending || syncPending

/** Why a queued meal can never be added. Locale-neutral: each platform maps these to its own copy. */
enum class PendingFailure {
    /** The plan or the recipe does not exist (any more). */
    NOT_FOUND,

    /** The server refused the meal (HTTP 400/422). */
    REJECTED,

    /** Anything else. */
    UNKNOWN,
}

/**
 * One add-meal request waiting to be sent (DPL-407).
 *
 * [recipe] and [nutritionalInfo] are only there so the plan can show the meal in the meantime.
 * [remoteMealId] is set once the server created the meal but its day is still to be set.
 */
data class PendingMeal(
    val id: Long,
    val planId: String,
    val mealType: String,
    val recipeId: String,
    val servings: Double,
    val dayIndex: Int?,
    val recipe: PlanMealRecipe,
    val nutritionalInfo: NutritionalInfo?,
    val attempts: Int,
    val remoteMealId: String?,
    val failure: PendingFailure?,
) {
    /** The id the plan shows this meal under until the server has one. */
    val tempMealId: String get() = "$PENDING_MEAL_ID_PREFIX$id"

    /** The meal as the plan shows it while it waits. */
    fun toPlanMeal() = PlanMeal(
        id = tempMealId,
        mealType = mealType,
        servings = servings,
        dayIndex = dayIndex,
        recipe = recipe,
        nutritionalInfo = nutritionalInfo,
    )

    /** The request that creates this meal on the server. */
    fun toRequest() = AddMealRequest(mealType = mealType, recipeId = recipeId, servings = servings)
}

/**
 * On-device queue of meals added while the server could not be reached (DPL-407), in the order they
 * were made. It survives the app being closed.
 */
class PendingMealStore(private val database: NutriPlanDatabase) {

    private val queries = database.pendingMealQueries

    /** Tolerant on read: a stored blob written by an older app version must never crash the app. */
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /** Queue [request] (with the [dayIndex] to place it on afterwards) and return the stored row. */
    fun enqueue(
        planId: String,
        request: AddMealRequest,
        dayIndex: Int?,
        recipe: PlanMealRecipe,
        nutritionalInfo: NutritionalInfo?,
    ): PendingMeal =
        database.transactionWithResult {
            queries.insertPending(
                plan_id = planId,
                meal_type = request.mealType,
                recipe_id = request.recipeId,
                servings = request.servings,
                day_index = dayIndex?.toLong(),
                recipe = json.encodeToString(PlanMealRecipe.serializer(), recipe),
                nutritional_info = nutritionalInfo?.let { json.encodeToString(NutritionalInfo.serializer(), it) },
            )
            val id = queries.selectLastId().executeAsOne()
            PendingMeal(
                id = id,
                planId = planId,
                mealType = request.mealType,
                recipeId = request.recipeId,
                servings = request.servings,
                dayIndex = dayIndex,
                recipe = recipe,
                nutritionalInfo = nutritionalInfo,
                attempts = 0,
                remoteMealId = null,
                failure = null,
            )
        }

    /** Every request still waiting to be sent, oldest first. */
    fun waiting(): List<PendingMeal> = queries.selectWaiting(::toPendingMeal).executeAsList()

    /** The waiting meals of [planId] that the plan should show as stand-ins, oldest first. */
    fun shownFor(planId: String): List<PendingMeal> = queries.selectShownForPlan(planId, ::toPendingMeal).executeAsList()

    /** The requests that can never succeed, oldest first, for the user to be told about. */
    fun failed(): List<PendingMeal> = queries.selectFailed(::toPendingMeal).executeAsList()

    /** Remember that the server created the meal as [remoteMealId], so a retry only sets its day. */
    fun markAdded(id: Long, remoteMealId: String) = queries.markAdded(remoteMealId, id)

    /** Count one more try that did not get through. */
    fun bumpAttempts(id: Long) = queries.bumpAttempts(id)

    /** Give up on a request: it stays stored, flagged with [failure], until it is dismissed. */
    fun markFailed(id: Long, failure: PendingFailure) = queries.markFailed(failure.name, id)

    /** Forget one request (sent, or dismissed by the user). */
    fun remove(id: Long) = queries.deleteById(id)

    /** Forget every request (for example on logout). */
    fun clear() = queries.deleteAll()

    @Suppress("LongParameterList")
    private fun toPendingMeal(
        id: Long,
        planId: String,
        mealType: String,
        recipeId: String,
        servings: Double,
        dayIndex: Long?,
        recipe: String,
        nutritionalInfo: String?,
        attempts: Long,
        remoteMealId: String?,
        failure: String?,
    ) = PendingMeal(
        id = id,
        planId = planId,
        mealType = mealType,
        recipeId = recipeId,
        servings = servings,
        dayIndex = dayIndex?.toInt(),
        recipe = runCatching { json.decodeFromString(PlanMealRecipe.serializer(), recipe) }
            .getOrElse { PlanMealRecipe(id = recipeId, name = "") },
        nutritionalInfo = nutritionalInfo?.let {
            runCatching { json.decodeFromString(NutritionalInfo.serializer(), it) }.getOrNull()
        },
        attempts = attempts.toInt(),
        remoteMealId = remoteMealId,
        failure = failure?.let { name -> PendingFailure.entries.firstOrNull { it.name == name } ?: PendingFailure.UNKNOWN },
    )
}
