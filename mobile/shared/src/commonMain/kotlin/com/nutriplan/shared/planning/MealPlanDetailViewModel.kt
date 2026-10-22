package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.toApiFailure
import com.nutriplan.shared.data.local.PendingChange
import com.nutriplan.shared.data.local.PendingMeal
import com.nutriplan.shared.data.repository.DietaryRepository
import com.nutriplan.shared.data.repository.PendingMealSync
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/** Why a plan could not be loaded. Locale-neutral: each platform maps these to its own copy. */
enum class MealPlanDetailError {
    /** The device could not reach the server and the plan is not saved on the device. */
    NETWORK,

    /** The server failed (HTTP 5xx) and the plan is not saved on the device. */
    SERVER_PROBLEM,

    /** The plan does not exist (any more): deleted on another device, or a stale link. */
    NOT_FOUND,

    /** The server rejected the session (HTTP 401): the user has to sign in again. */
    SESSION_EXPIRED,

    /** Anything else. */
    UNKNOWN,
}

/**
 * Observable state of the plan detail screen (DPL-505).
 *
 * Like the list, a failed refresh keeps the plan that is already on screen; [error] then describes
 * the failed refresh.
 */
data class MealPlanDetailUiState(
    val plan: MealPlan? = null,
    val days: List<MealPlanDay> = emptyList(),
    val isLoading: Boolean = true,
    val isRefreshing: Boolean = false,
    val error: MealPlanDetailError? = null,
    /** Meals added while offline that the server then refused: they left the plan and the user is told. */
    val failedAdds: List<PendingMeal> = emptyList(),
    /** Edits and removals made while offline that the server then refused: the plan shows the server's version. */
    val failedChanges: List<PendingChange> = emptyList(),
) {
    /** The plan loaded but has no meals yet. */
    val hasNoMeals: Boolean get() = plan != null && days.isEmpty()
}

/** Maps a thrown repository failure to a stable, localizable [MealPlanDetailError]. */
fun Throwable.toMealPlanDetailError(): MealPlanDetailError = when (toApiFailure()) {
    ApiFailure.OFFLINE -> MealPlanDetailError.NETWORK
    ApiFailure.SERVER -> MealPlanDetailError.SERVER_PROBLEM
    ApiFailure.SESSION_EXPIRED -> MealPlanDetailError.SESSION_EXPIRED
    ApiFailure.NOT_FOUND -> MealPlanDetailError.NOT_FOUND
    else -> MealPlanDetailError.UNKNOWN
}

/**
 * Shared logic of the plan detail screen used by the Compose (DPL-505) and SwiftUI screens.
 *
 * Reads through [DietaryRepository]; with the cached repository wired the plan is served from the
 * device when the server cannot be reached. The functions are `suspend` so the UI owns the scope;
 * [CancellationException] is rethrown so leaving the screen cancels cleanly.
 */
class MealPlanDetailViewModel(
    private val repository: DietaryRepository,
    /** When given, meals queued while offline are sent whenever the plan is loaded (DPL-407). */
    private val sync: PendingMealSync? = null,
) {

    private val _state = MutableStateFlow(MealPlanDetailUiState())
    val state: StateFlow<MealPlanDetailUiState> = _state.asStateFlow()

    private var planId: String? = null

    /** First load of [planId], or a retry after a failure. */
    suspend fun load(planId: String) {
        this.planId = planId
        _state.update { it.copy(isLoading = it.plan == null, error = null) }
        flushQueued()
        fetch(planId)
    }

    /** Pull-to-refresh of the plan passed to [load]; keeps the current plan visible. */
    suspend fun refresh() {
        val id = planId ?: return
        _state.update { it.copy(isRefreshing = true, error = null) }
        flushQueued()
        fetch(id)
    }

    /** Stop telling the user about an edit or removal that could not be saved. */
    fun dismissFailedChange(id: Long) {
        sync?.dismissChangeFailure(id)
        _state.update { state -> state.copy(failedChanges = state.failedChanges.filter { it.id != id }) }
    }

    /** Stop telling the user about a meal that could not be added. */
    fun dismissFailedAdd(id: Long) {
        sync?.dismissFailure(id)
        _state.update { state -> state.copy(failedAdds = state.failedAdds.filter { it.id != id }) }
    }

    /**
     * Send the meals added while offline, so the plan read that follows already has them. Best
     * effort: a failure leaves them queued and never blocks showing the plan.
     */
    private suspend fun flushQueued() {
        try {
            sync?.flush()
        } catch (e: CancellationException) {
            _state.update { it.copy(isLoading = false, isRefreshing = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught", "SwallowedException") e: Exception) {
            // Stays queued; the next load tries again.
        }
    }

    private suspend fun fetch(planId: String) {
        try {
            val plan = repository.getMealPlan(planId)
            _state.update {
                MealPlanDetailUiState(
                    plan = plan,
                    days = groupMealsByDay(plan.startDate, plan.meals),
                    isLoading = false,
                    failedAdds = sync?.failures(planId).orEmpty(),
                    failedChanges = sync?.changeFailures(planId).orEmpty(),
                )
            }
        } catch (e: CancellationException) {
            _state.update { it.copy(isLoading = false, isRefreshing = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            val error = e.toMealPlanDetailError()
            _state.update {
                // A plan that no longer exists must not stay on screen as if it were current.
                val keep = it.takeIf { error != MealPlanDetailError.NOT_FOUND }
                MealPlanDetailUiState(
                    plan = keep?.plan,
                    days = keep?.days.orEmpty(),
                    isLoading = false,
                    error = error,
                    failedAdds = sync?.failures(planId).orEmpty(),
                    failedChanges = sync?.changeFailures(planId).orEmpty(),
                )
            }
        }
    }
}
