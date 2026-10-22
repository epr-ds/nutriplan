package com.nutriplan.shared.data.local

import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.UpdateMealRequest
import com.nutriplan.shared.data.model.scaledBy

/** What a queued change does to a meal that is on the server. */
enum class ChangeKind { UPDATE, REMOVE }

/**
 * One edit or removal of a meal waiting to be sent (DPL-407). For an [ChangeKind.UPDATE] a null
 * field means "leave it as it is", exactly like the API's partial update.
 */
data class PendingChange(
    val id: Long,
    val planId: String,
    val mealId: String,
    val mealType: String,
    val kind: ChangeKind,
    val servings: Double?,
    val dayIndex: Int?,
    val satisfactionLevel: Int?,
    val attempts: Int,
    val failure: PendingFailure?,
) {
    /** The partial update to send for an [ChangeKind.UPDATE]. */
    fun toRequest() = UpdateMealRequest(servings = servings, dayIndex = dayIndex, satisfactionLevel = satisfactionLevel)

    /** [meal] as the plan shows it with this change applied (the removal itself is the caller's job). */
    fun applyTo(meal: PlanMeal): PlanMeal {
        if (kind != ChangeKind.UPDATE) return meal
        val newServings = servings ?: meal.servings
        return meal.copy(
            servings = newServings,
            dayIndex = dayIndex ?: meal.dayIndex,
            satisfactionLevel = satisfactionLevel ?: meal.satisfactionLevel,
            // The server's nutrition is per serving times servings, so it follows the servings.
            nutritionalInfo = meal.nutritionalInfo?.takeIf { servings != null }?.scaledBy(newServings / meal.servings)
                ?: meal.nutritionalInfo,
            syncPending = true,
        )
    }
}

/**
 * On-device queue of edits and removals of meals made while the server could not be reached
 * (DPL-407). It keeps **at most one waiting change per meal**, so the plan and the later flush agree:
 * - a newer edit is merged into the waiting one, field by field (the last write wins);
 * - a removal replaces everything waiting for that meal;
 * - an edit of a meal that is already queued for removal changes nothing.
 */
class PendingChangeStore(private val database: NutriPlanDatabase) {

    private val queries = database.pendingChangeQueries

    /** Queue (or merge) the edit [request] of [meal] in [planId]. */
    fun queueUpdate(planId: String, meal: PlanMeal, request: UpdateMealRequest): PendingChange =
        database.transactionWithResult {
            val existing = queries.selectWaitingForMeal(planId, meal.id, ::toPendingChange).executeAsList()
            val removal = existing.firstOrNull { it.kind == ChangeKind.REMOVE }
            val edit = existing.firstOrNull { it.kind == ChangeKind.UPDATE }
            when {
                removal != null -> removal
                edit != null -> {
                    val merged = edit.copy(
                        servings = request.servings ?: edit.servings,
                        dayIndex = request.dayIndex ?: edit.dayIndex,
                        satisfactionLevel = request.satisfactionLevel ?: edit.satisfactionLevel,
                    )
                    queries.updateFields(merged.servings, merged.dayIndex?.toLong(), merged.satisfactionLevel?.toLong(), edit.id)
                    merged
                }
                else -> insert(planId, meal, ChangeKind.UPDATE, request)
            }
        }

    /** Queue the removal of [meal] from [planId], replacing anything waiting for it. */
    fun queueRemove(planId: String, meal: PlanMeal): PendingChange =
        database.transactionWithResult {
            queries.deleteWaitingForMeal(planId, meal.id)
            insert(planId, meal, ChangeKind.REMOVE, UpdateMealRequest())
        }

    /** Every change still waiting to be sent, oldest first. */
    fun waiting(): List<PendingChange> = queries.selectWaiting(::toPendingChange).executeAsList()

    /** The waiting changes of [planId], for the plan to show them as already made. */
    fun waitingFor(planId: String): List<PendingChange> =
        queries.selectWaitingForPlan(planId, ::toPendingChange).executeAsList()

    /** The changes that can never succeed, for the user to be told about. */
    fun failed(): List<PendingChange> = queries.selectFailed(::toPendingChange).executeAsList()

    /** Count one more try that did not get through. */
    fun bumpAttempts(id: Long) = queries.bumpAttempts(id)

    /** Give up on a change: it stays stored, flagged with [failure], until it is dismissed. */
    fun markFailed(id: Long, failure: PendingFailure) = queries.markFailed(failure.name, id)

    /** Forget one change (sent, or dismissed by the user). */
    fun remove(id: Long) = queries.deleteById(id)

    /** Forget every change (for example on logout). */
    fun clear() = queries.deleteAll()

    private fun insert(planId: String, meal: PlanMeal, kind: ChangeKind, request: UpdateMealRequest): PendingChange {
        queries.insertChange(
            plan_id = planId,
            meal_id = meal.id,
            meal_type = meal.mealType,
            kind = kind.name,
            servings = request.servings,
            day_index = request.dayIndex?.toLong(),
            satisfaction_level = request.satisfactionLevel?.toLong(),
        )
        return PendingChange(
            id = queries.selectLastId().executeAsOne(),
            planId = planId,
            mealId = meal.id,
            mealType = meal.mealType,
            kind = kind,
            servings = request.servings,
            dayIndex = request.dayIndex,
            satisfactionLevel = request.satisfactionLevel,
            attempts = 0,
            failure = null,
        )
    }

    @Suppress("LongParameterList")
    private fun toPendingChange(
        id: Long,
        planId: String,
        mealId: String,
        mealType: String,
        kind: String,
        servings: Double?,
        dayIndex: Long?,
        satisfactionLevel: Long?,
        attempts: Long,
        failure: String?,
    ) = PendingChange(
        id = id,
        planId = planId,
        mealId = mealId,
        mealType = mealType,
        kind = ChangeKind.entries.firstOrNull { it.name == kind } ?: ChangeKind.UPDATE,
        servings = servings,
        dayIndex = dayIndex?.toInt(),
        satisfactionLevel = satisfactionLevel?.toInt(),
        attempts = attempts.toInt(),
        failure = failure?.let { name -> PendingFailure.entries.firstOrNull { it.name == name } ?: PendingFailure.UNKNOWN },
    )
}
