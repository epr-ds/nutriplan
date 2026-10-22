package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.toApiFailure
import com.nutriplan.shared.data.repository.DietaryRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/**
 * Why the meal plans could not be loaded. Locale-neutral: each platform maps these codes to its
 * own localized microcopy (IDN-902 convention).
 */
enum class MealPlanListError {
    /** The device could not reach the server and nothing is saved on the device yet. */
    NETWORK,

    /** The server failed (HTTP 5xx) and nothing is saved on the device yet. */
    SERVER_PROBLEM,

    /** The server rejected the session (HTTP 401): the user has to sign in again. */
    SESSION_EXPIRED,

    /** Anything else. */
    UNKNOWN,
}

/**
 * Observable state of the meal plan list (DPL-501).
 *
 * Existing [plans] stay visible while a refresh runs or after a refresh fails, so a pull-to-refresh
 * on a bad connection never blanks the screen; [error] then describes the failed refresh.
 */
data class MealPlanListUiState(
    val plans: List<MealPlanSummary> = emptyList(),
    val isLoading: Boolean = true,
    val isRefreshing: Boolean = false,
    val error: MealPlanListError? = null,
) {
    /** The first load finished without error and there are no plans yet. */
    val isEmpty: Boolean get() = !isLoading && error == null && plans.isEmpty()
}

/** Maps a thrown repository failure to a stable, localizable [MealPlanListError]. */
fun Throwable.toMealPlanListError(): MealPlanListError = when (toApiFailure()) {
    ApiFailure.OFFLINE -> MealPlanListError.NETWORK
    ApiFailure.SERVER -> MealPlanListError.SERVER_PROBLEM
    ApiFailure.SESSION_EXPIRED -> MealPlanListError.SESSION_EXPIRED
    else -> MealPlanListError.UNKNOWN
}

/**
 * Shared logic of the meal plan list used by the Compose (DPL-501) and SwiftUI screens.
 *
 * Reads through [DietaryRepository]; when the app wires the cached repository, plans are served
 * from the device if the server cannot be reached. The functions are `suspend` so the UI owns the
 * coroutine scope; [CancellationException] is rethrown so leaving the screen cancels cleanly.
 */
class MealPlanListViewModel(
    private val repository: DietaryRepository,
) {

    private val _state = MutableStateFlow(MealPlanListUiState())
    val state: StateFlow<MealPlanListUiState> = _state.asStateFlow()

    /** First load, or retry after a failure: shows the loading state unless plans are on screen. */
    suspend fun load() {
        _state.update { it.copy(isLoading = it.plans.isEmpty(), error = null) }
        fetch()
    }

    /** Pull-to-refresh: keeps the current plans visible while the request runs. */
    suspend fun refresh() {
        _state.update { it.copy(isRefreshing = true, error = null) }
        fetch()
    }

    private suspend fun fetch() {
        try {
            val plans = repository.getMealPlans()
            _state.update { MealPlanListUiState(plans = plans, isLoading = false) }
        } catch (e: CancellationException) {
            _state.update { it.copy(isLoading = false, isRefreshing = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update {
                it.copy(
                    isLoading = false,
                    isRefreshing = false,
                    error = e.toMealPlanListError(),
                )
            }
        }
    }
}

/**
 * AIA-604: the plans a meal can be added to, i.e. still being planned (`draft`) or under way
 * (`active`); `completed` and `saved` plans are finished.
 */
val MealPlanListUiState.plansOpenForMeals: List<MealPlanSummary>
    get() = plans.filter { it.status.lowercase() in OPEN_FOR_MEALS }

private val OPEN_FOR_MEALS = setOf("draft", "active")
