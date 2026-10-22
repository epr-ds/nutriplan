package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.local.ChangeKind
import com.nutriplan.shared.data.local.MealPlanCache
import com.nutriplan.shared.data.local.PendingChange
import com.nutriplan.shared.data.local.PendingChangeStore
import com.nutriplan.shared.data.local.PendingFailure
import com.nutriplan.shared.data.local.PendingMeal
import com.nutriplan.shared.data.local.PendingMealStore
import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.scaledBy
import com.nutriplan.shared.data.model.PlanMealRecipe
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.model.UpdateMealRequest
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.toApiFailure
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlin.coroutines.cancellation.CancellationException

/** What one [PendingMealSync.flush] did. */
data class FlushResult(
    /** Meals that reached the server. */
    val added: Int,
    /** Meals given up on because they can never succeed (see [PendingMealSync.failures]). */
    val failed: Int,
    /** Meals still waiting, because the server could not be reached or the session ended. */
    val waiting: Int,
)

/**
 * Meals added while the server could not be reached (DPL-407): queued on the device, shown in the
 * plan meanwhile, and sent when the server can be reached again.
 *
 * - [queueAdd] stores the request and returns at once, so adding a meal never waits for the network.
 * - [flush] sends the queue in the order it was made. A request the server cannot be reached for
 *   (offline, a 5xx, a rejected session) stays queued and stops the run, so order is kept. A request
 *   that can never succeed (the plan or recipe is gone, or the server refuses it) is flagged with a
 *   [PendingFailure] and kept for the user to see; the run goes on. This is the rollback: the stand-in
 *   meal leaves the plan and the user is told why. A meal the server created whose day could not be
 *   set yet is remembered, so a retry only sets the day and never adds the meal twice.
 * - When the server has the meal, the plan is read fresh: the server's data wins, and the queued
 *   changes that are still waiting are applied on top of it (last write wins).
 *
 * Nothing here listens for connectivity: callers flush when it is natural to retry, such as when a
 * plan is opened or refreshed. Two flushes never run at the same time.
 */
class PendingMealSync(
    private val remote: DietaryRepository,
    private val store: PendingMealStore,
    private val cache: MealPlanCache,
    /** Asked to send the queue once the server can be reached, even if the app is closed by then. */
    private val scheduler: SyncScheduler = SyncScheduler.None,
    /** Edits and removals of meals made while offline; without it those still need a connection. */
    private val changes: PendingChangeStore? = null,
) : MealQueueFlusher {

    private val flushing = Mutex()

    /** Queue adding [recipe] to [planId]; the plan shows it straight away as a waiting meal. */
    fun queueAdd(planId: String, request: AddMealRequest, dayIndex: Int?, recipe: Recipe): PendingMeal =
        store.enqueue(
            planId = planId,
            request = request,
            dayIndex = dayIndex,
            recipe = PlanMealRecipe(id = recipe.id, name = recipe.name, imageUrl = recipe.imageUrl),
            nutritionalInfo = recipe.nutritionalInfo?.scaledBy(request.servings),
        ).also { scheduler.requestSync() }

    /** Ask the platform to send the queue when the server can be reached (for example when the app starts). */
    fun requestSync() = scheduler.requestSync()

    /** Queue the edit [request] of [meal] (or merge it into the one already waiting). */
    fun queueUpdate(planId: String, meal: PlanMeal, request: UpdateMealRequest): PendingChange? =
        changes?.queueUpdate(planId, meal, request)?.also { scheduler.requestSync() }

    /** Queue the removal of [meal], replacing anything waiting for it. */
    fun queueRemove(planId: String, meal: PlanMeal): PendingChange? =
        changes?.queueRemove(planId, meal)?.also { scheduler.requestSync() }

    /** Whether edits and removals can be queued at all. */
    val canQueueChanges: Boolean get() = changes != null

    /** Whether anything is waiting to be sent. */
    fun hasWaiting(): Boolean = waitingCount() > 0

    private fun waitingCount(): Int = store.waiting().size + changes?.waiting().orEmpty().size

    /** The meals that can never be added, optionally only those of [planId]. */
    fun failures(planId: String? = null): List<PendingMeal> =
        store.failed().filter { planId == null || it.planId == planId }

    /** Stop telling the user about a failed meal. */
    fun dismissFailure(id: Long) = store.remove(id)

    /** The edits and removals that can never be applied, optionally only those of [planId]. */
    fun changeFailures(planId: String? = null): List<PendingChange> =
        changes?.failed().orEmpty().filter { planId == null || it.planId == planId }

    /** Stop telling the user about a failed edit or removal. */
    fun dismissChangeFailure(id: Long) {
        changes?.remove(id)
    }

    /** Send what is waiting, oldest first. Safe to call often: it does nothing when the queue is empty. */
    override suspend fun flush(): FlushResult = flushing.withLock {
        var added = 0
        var failed = 0
        for (pending in store.waiting()) {
            try {
                send(pending)
                added++
            } catch (e: CancellationException) {
                throw e
            } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
                val failure = e.toApiFailure()
                if (failure.isTemporary()) {
                    // Not the request's fault: keep it, and keep the order by not trying later ones.
                    store.bumpAttempts(pending.id)
                    return@withLock FlushResult(added, failed, waiting = waitingCount())
                }
                store.markFailed(pending.id, failure.toPendingFailure())
                failed++
            }
        }
        // Edits and removals of meals that are already on the server go after the new meals.
        for (change in changes?.waiting().orEmpty()) {
            try {
                send(change)
                added++
            } catch (e: CancellationException) {
                throw e
            } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
                val failure = e.toApiFailure()
                if (failure.isTemporary()) {
                    changes?.bumpAttempts(change.id)
                    return@withLock FlushResult(added, failed, waiting = waitingCount())
                }
                if (change.kind == ChangeKind.REMOVE && failure == ApiFailure.NOT_FOUND) {
                    // Already gone is what the user wanted.
                    changes?.remove(change.id)
                    cache.invalidateDetail(change.planId)
                    added++
                } else {
                    changes?.markFailed(change.id, failure.toPendingFailure())
                    failed++
                }
            }
        }
        FlushResult(added, failed, waiting = 0)
    }

    /** Apply one queued edit or removal on the server, then forget it. */
    private suspend fun send(change: PendingChange) {
        when (change.kind) {
            ChangeKind.UPDATE -> remote.updateMeal(change.planId, change.mealId, change.toRequest())
            ChangeKind.REMOVE -> remote.removeMeal(change.planId, change.mealId)
        }
        cache.invalidateDetail(change.planId)
        changes?.remove(change.id)
    }

    /** Create the meal on the server (unless it already is there), set its day, and forget the request. */
    private suspend fun send(pending: PendingMeal) {
        val mealId = pending.remoteMealId ?: remote.addMeal(pending.planId, pending.toRequest()).id.also {
            store.markAdded(pending.id, it)
        }
        pending.dayIndex?.let { day ->
            remote.updateMeal(pending.planId, mealId, UpdateMealRequest(dayIndex = day))
        }
        // The plan changed on the server: the saved copy of it is stale.
        cache.invalidateDetail(pending.planId)
        store.remove(pending.id)
    }

    private fun ApiFailure.isTemporary(): Boolean =
        this == ApiFailure.OFFLINE || this == ApiFailure.SERVER || this == ApiFailure.SESSION_EXPIRED

    private fun ApiFailure.toPendingFailure(): PendingFailure = when (this) {
        ApiFailure.NOT_FOUND -> PendingFailure.NOT_FOUND
        ApiFailure.REJECTED -> PendingFailure.REJECTED
        else -> PendingFailure.UNKNOWN
    }
}
