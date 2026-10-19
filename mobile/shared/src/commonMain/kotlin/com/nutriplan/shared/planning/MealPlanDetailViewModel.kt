package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.repository.DietaryRepository
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
) {
    /** The plan loaded but has no meals yet. */
    val hasNoMeals: Boolean get() = plan != null && days.isEmpty()
}

/** Maps a thrown repository failure to a stable, localizable [MealPlanDetailError]. */
fun Throwable.toMealPlanDetailError(): MealPlanDetailError = when (this) {
    is ApiException.HttpError -> when (statusCode) {
        401 -> MealPlanDetailError.SESSION_EXPIRED
        404 -> MealPlanDetailError.NOT_FOUND
        in 500..599 -> MealPlanDetailError.SERVER_PROBLEM
        else -> MealPlanDetailError.UNKNOWN
    }
    is ApiException.NetworkError -> MealPlanDetailError.NETWORK
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
) {

    private val _state = MutableStateFlow(MealPlanDetailUiState())
    val state: StateFlow<MealPlanDetailUiState> = _state.asStateFlow()

    private var planId: String? = null

    /** First load of [planId], or a retry after a failure. */
    suspend fun load(planId: String) {
        this.planId = planId
        _state.update { it.copy(isLoading = it.plan == null, error = null) }
        fetch(planId)
    }

    /** Pull-to-refresh of the plan passed to [load]; keeps the current plan visible. */
    suspend fun refresh() {
        val id = planId ?: return
        _state.update { it.copy(isRefreshing = true, error = null) }
        fetch(id)
    }

    private suspend fun fetch(planId: String) {
        try {
            val plan = repository.getMealPlan(planId)
            _state.update {
                MealPlanDetailUiState(
                    plan = plan,
                    days = groupMealsByDay(plan.meals.orEmpty()),
                    isLoading = false,
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
                )
            }
        }
    }
}
