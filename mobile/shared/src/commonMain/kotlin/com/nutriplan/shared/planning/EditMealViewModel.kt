package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.UpdateMealRequest
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.toApiFailure
import com.nutriplan.shared.data.repository.DietaryRepository
import com.nutriplan.shared.data.repository.PendingMealSync
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/** A problem with one field of the edit-meal form, shown inline. Locale-neutral. */
enum class EditMealFieldError {
    SERVINGS_REQUIRED,
    SERVINGS_INVALID,
}

/** Why a meal could not be loaded, changed or removed. Locale-neutral. */
enum class EditMealError {
    /** The device could not reach the server. Meals cannot be changed offline (yet). */
    NETWORK,

    /** The server failed (HTTP 5xx). */
    SERVER_PROBLEM,

    /** The server rejected the session (HTTP 401): the user has to sign in again. */
    SESSION_EXPIRED,

    /** The plan or the meal does not exist (any more). */
    NOT_FOUND,

    /** The server refused the content (HTTP 400/422) although the app's own checks passed. */
    REJECTED,

    /** Anything else. */
    UNKNOWN,
}

/**
 * Observable state of the edit-meal form (DPL-508 and meal editing).
 *
 * [servings] is the raw text of the field. [satisfaction] is the 1 to 5 rating, or null while the
 * meal is unrated. [isDone] tells the screen to leave (after a save, a removal, or when nothing
 * changed).
 */
data class EditMealUiState(
    /** The meal as the server has it; the form edits a copy. */
    val meal: PlanMeal? = null,
    val days: List<PlanDayOption> = emptyList(),
    val isLoading: Boolean = true,
    /** Why the meal could not be loaded; the form is not usable then. */
    val loadError: EditMealError? = null,
    val servings: String = "",
    val dayIndex: Int? = null,
    val satisfaction: Int? = null,
    val servingsError: EditMealFieldError? = null,
    val isSaving: Boolean = false,
    val isRemoving: Boolean = false,
    val error: EditMealError? = null,
    /** The change was saved on this device because the server could not be reached; it is sent later. */
    val queued: Boolean = false,
    val isDone: Boolean = false,
) {
    /** The API can place a meal on a day but not take it off one again. */
    val canClearDay: Boolean get() = meal?.dayIndex == null

    /** Something differs from what the server has. */
    val hasChanges: Boolean
        get() = meal != null && (
            servings.toDoubleOrNull().let { it != null && it != meal.servings } ||
                dayIndex != meal.dayIndex ||
                satisfaction != meal.satisfactionLevel
            )
}

/** Maps a thrown repository failure to a stable, localizable [EditMealError]. */
fun Throwable.toEditMealError(): EditMealError = when (toApiFailure()) {
    ApiFailure.OFFLINE -> EditMealError.NETWORK
    ApiFailure.SERVER -> EditMealError.SERVER_PROBLEM
    ApiFailure.SESSION_EXPIRED -> EditMealError.SESSION_EXPIRED
    ApiFailure.NOT_FOUND -> EditMealError.NOT_FOUND
    ApiFailure.REJECTED -> EditMealError.REJECTED
    else -> EditMealError.UNKNOWN
}

/**
 * Shared logic of the edit-meal form used by the Compose and SwiftUI screens: change a planned
 * meal's servings and day, rate how satisfying it was (1 to 5, DPL-508), or remove it.
 *
 * - [start] reads the plan (from the device when offline) and takes the meal out of it, plus the
 *   plan's days for the day choice.
 * - [save] sends one request with only the fields that changed, and does nothing at all (just
 *   finishes) when nothing changed. A day can be set or changed but not cleared, and a rating can be
 *   set or changed but not cleared: the API has no way to express either.
 * - [remove] deletes the meal; a meal that is already gone counts as removed.
 * - Meals cannot be changed offline; the form says so instead of queueing something it cannot send.
 *
 * The functions are `suspend` so the UI owns the coroutine scope; [CancellationException] is
 * rethrown so leaving the screen cancels cleanly.
 */
class EditMealViewModel(
    private val repository: DietaryRepository,
    /** When given, a change that cannot reach the server is queued instead of failing (DPL-407). */
    private val sync: PendingMealSync? = null,
) {

    private val _state = MutableStateFlow(EditMealUiState())
    val state: StateFlow<EditMealUiState> = _state.asStateFlow()

    private var planId: String? = null

    /** The current UI state, for callers that read rather than observe it (e.g. the SwiftUI bridge). */
    fun currentState(): EditMealUiState = _state.value

    /** Load [mealId] of [planId]; also the retry after a failed load. */
    suspend fun start(planId: String, mealId: String) {
        this.planId = planId
        _state.update { it.copy(isLoading = it.meal == null, loadError = null) }
        try {
            val plan = repository.getMealPlan(planId)
            val meal = plan.meals.firstOrNull { it.id == mealId }
            if (meal == null) {
                _state.update { it.copy(isLoading = false, loadError = EditMealError.NOT_FOUND) }
                return
            }
            _state.update { current ->
                if (current.meal != null) {
                    // A retry: keep what the user already edited.
                    current.copy(isLoading = false)
                } else {
                    current.copy(
                        meal = meal,
                        days = planDays(plan.startDate, plan.endDate),
                        isLoading = false,
                        servings = formatServings(meal.servings),
                        dayIndex = meal.dayIndex,
                        satisfaction = meal.satisfactionLevel,
                    )
                }
            }
        } catch (e: CancellationException) {
            _state.update { it.copy(isLoading = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(isLoading = false, loadError = e.toEditMealError()) }
        }
    }

    fun onServingsChange(value: String) {
        // The form is not usable while the meal is loading or failed to load, so it takes no edits.
        if (_state.value.isLoading || _state.value.loadError != null) return
        _state.update { it.copy(servings = value.decimalOnly(), servingsError = null, error = null) }
    }

    /** Choose the day of the plan (0-based). Clearing it (null) is only possible while the meal has none. */
    fun onDayChange(dayIndex: Int?) {
        if (_state.value.isLoading || _state.value.loadError != null) return
        _state.update { state ->
            val valid = dayIndex?.takeIf { index -> state.days.any { it.dayIndex == index } }
            if (valid == null && !state.canClearDay) return@update state
            state.copy(dayIndex = valid, error = null)
        }
    }

    /** Rate the meal from 1 to 5; anything else is ignored. */
    fun onSatisfactionChange(level: Int) {
        // The form is not usable while the meal is loading or failed to load, so it takes no edits.
        if (_state.value.isLoading || _state.value.loadError != null) return
        if (level !in MIN_SATISFACTION..MAX_SATISFACTION) return
        _state.update { it.copy(satisfaction = level, error = null) }
    }

    /** Save the changes. Does nothing while busy or once finished. */
    suspend fun save() {
        val current = _state.value
        val meal = current.meal ?: return
        if (current.isSaving || current.isRemoving || current.isDone) return
        val planId = planId ?: return

        val servingsError = servingsError(current.servings)
        if (servingsError != null) {
            _state.update { it.copy(servingsError = servingsError) }
            return
        }
        val servings = current.servings.toDouble()
        val request = UpdateMealRequest(
            servings = servings.takeIf { it != meal.servings },
            dayIndex = current.dayIndex.takeIf { it != meal.dayIndex },
            satisfactionLevel = current.satisfaction.takeIf { it != meal.satisfactionLevel },
        )
        if (request == UpdateMealRequest()) {
            _state.update { it.copy(isDone = true) }
            return
        }

        _state.update { it.copy(isSaving = true, error = null) }
        try {
            repository.updateMeal(planId, meal.id, request)
            _state.update { it.copy(isSaving = false, isDone = true) }
        } catch (e: CancellationException) {
            _state.update { it.copy(isSaving = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            if (canQueue(e) && sync?.queueUpdate(planId, meal, request) != null) {
                _state.update { it.copy(isSaving = false, queued = true, isDone = true) }
            } else {
                _state.update { it.copy(isSaving = false, error = e.toEditMealError()) }
            }
        }
    }

    /** Remove the meal from the plan. Does nothing while busy or once finished. */
    suspend fun remove() {
        val current = _state.value
        val meal = current.meal ?: return
        if (current.isSaving || current.isRemoving || current.isDone) return
        val planId = planId ?: return

        _state.update { it.copy(isRemoving = true, error = null) }
        try {
            repository.removeMeal(planId, meal.id)
            _state.update { it.copy(isRemoving = false, isDone = true) }
        } catch (e: CancellationException) {
            _state.update { it.copy(isRemoving = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            val error = e.toEditMealError()
            if (canQueue(e) && sync?.queueRemove(planId, meal) != null) {
                _state.update { it.copy(isRemoving = false, queued = true, isDone = true) }
            } else if (error == EditMealError.NOT_FOUND) {
                // Already gone is what the user wanted.
                _state.update { it.copy(isRemoving = false, isDone = true) }
            } else {
                _state.update { it.copy(isRemoving = false, error = error) }
            }
        }
    }

    /** The server could not be reached (offline or a 5xx) and changes can be queued for later. */
    private fun canQueue(e: Exception): Boolean =
        sync?.canQueueChanges == true && e.toApiFailure().let { it == ApiFailure.OFFLINE || it == ApiFailure.SERVER }

    private fun servingsError(text: String): EditMealFieldError? {
        if (text.isBlank()) return EditMealFieldError.SERVINGS_REQUIRED
        val value = text.toDoubleOrNull() ?: return EditMealFieldError.SERVINGS_INVALID
        return if (value <= 0.0 || value > MAX_SERVINGS) EditMealFieldError.SERVINGS_INVALID else null
    }

    companion object {
        const val MIN_SATISFACTION = 1
        const val MAX_SATISFACTION = 5

        private const val MAX_SERVINGS = 99.0
    }
}

/** "2" for 2.0 and "1.5" for 1.5, so whole quantities have no trailing ".0". */
private fun formatServings(value: Double): String =
    if (value % 1.0 == 0.0) value.toInt().toString() else value.toString()

/** Keeps digits and at most one decimal point, limited in length. */
private fun String.decimalOnly(): String {
    var seenDot = false
    return filter { c ->
        when {
            c.isDigit() -> true
            c == '.' && !seenDot -> true.also { seenDot = true }
            else -> false
        }
    }.take(5)
}
