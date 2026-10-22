package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.Recipe
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

/** A problem with one field of the add-meal form, shown inline. Locale-neutral (IDN-902 convention). */
enum class AddMealFieldError {
    MEAL_TYPE_REQUIRED,
    SERVINGS_REQUIRED,
    SERVINGS_INVALID,
}

/** Why a recipe, or the meal, could not be loaded or added. Locale-neutral. */
enum class AddMealError {
    /** The device could not reach the server. Meals cannot be added offline (yet). */
    NETWORK,

    /** The server failed (HTTP 5xx). */
    SERVER_PROBLEM,

    /** The server rejected the session (HTTP 401): the user has to sign in again. */
    SESSION_EXPIRED,

    /** The recipe or the plan does not exist (any more). */
    NOT_FOUND,

    /** The server refused the content (HTTP 400/422) although the app's own checks passed. */
    REJECTED,

    /** Anything else. */
    UNKNOWN,
}

/** One day of the plan the meal can be placed on. */
data class PlanDayOption(
    /** 0-based day within the plan, as the API expects. */
    val dayIndex: Int,
    /** ISO date (`yyyy-MM-dd`) of that day. */
    val date: String,
)

/**
 * Observable state of the add-meal form (DPL-507).
 *
 * [servings] is the raw text of the field. [dayIndex] is optional: a meal without a day is allowed
 * (the plan shows it as unassigned). The API places a meal on a day with a second request, so the
 * meal can be [addedMealId] while [error] says the day could not be set; the form then only offers
 * to retry that step, never to add the meal twice. [isDone] tells the screen to leave.
 */
data class AddMealUiState(
    val recipe: Recipe? = null,
    val days: List<PlanDayOption> = emptyList(),
    val isLoading: Boolean = true,
    /** Why the recipe could not be loaded; the form is not usable then. */
    val loadError: AddMealError? = null,
    /** One of [AddMealViewModel.MEAL_TYPES], or null until the user chooses. */
    val mealType: String? = null,
    val servings: String = "1",
    val dayIndex: Int? = null,
    val mealTypeError: AddMealFieldError? = null,
    val servingsError: AddMealFieldError? = null,
    val isSaving: Boolean = false,
    val error: AddMealError? = null,
    /** Set as soon as the server created the meal. */
    val addedMealId: String? = null,
    /** The meal was saved on this device because the server could not be reached; it is sent later. */
    val queued: Boolean = false,
    val isDone: Boolean = false,
) {
    /** The meal exists but the chosen day could not be set on it. */
    val dayNotSet: Boolean get() = addedMealId != null && !isDone && error != null
}

/** Maps a thrown repository failure to a stable, localizable [AddMealError]. */
fun Throwable.toAddMealError(): AddMealError = when (toApiFailure()) {
    ApiFailure.OFFLINE -> AddMealError.NETWORK
    ApiFailure.SERVER -> AddMealError.SERVER_PROBLEM
    ApiFailure.SESSION_EXPIRED -> AddMealError.SESSION_EXPIRED
    ApiFailure.NOT_FOUND -> AddMealError.NOT_FOUND
    ApiFailure.REJECTED -> AddMealError.REJECTED
    else -> AddMealError.UNKNOWN
}

/**
 * Shared logic of the add-meal form used by the Compose (DPL-507) and SwiftUI screens: add a recipe
 * to a plan as a meal of a type, with servings and (optionally) a day.
 *
 * - [start] loads the recipe, and the plan's days for the day choice. Without the plan (for example
 *   a failed request) the form still works and the meal is left without a day.
 * - [save] checks the form, adds the meal, then places it on the chosen day. If only the second
 *   step fails the meal is kept ([AddMealUiState.addedMealId]) and calling [save] again retries just
 *   the day, so a retry can never add the meal twice.
 * - Meals cannot be added offline; the form says so instead of queueing something it cannot send.
 *
 * The functions are `suspend` so the UI owns the coroutine scope; [CancellationException] is
 * rethrown so leaving the screen cancels cleanly.
 */
class AddMealViewModel(
    private val repository: DietaryRepository,
    /** When given, an add that cannot reach the server is queued instead of failing (DPL-407). */
    private val sync: PendingMealSync? = null,
) {

    private val _state = MutableStateFlow(AddMealUiState())
    val state: StateFlow<AddMealUiState> = _state.asStateFlow()

    private var planId: String? = null
    private var recipeId: String? = null

    /**
     * Load [recipeId] and the days of [planId]; also the retry after a failed load. A known
     * [mealType] (an AI recommendation for one meal, AIA-604) is chosen unless the user already
     * picked one.
     */
    suspend fun start(planId: String, recipeId: String, mealType: String? = null) {
        this.planId = planId
        this.recipeId = recipeId
        _state.update { state ->
            state.copy(
                isLoading = state.recipe == null,
                loadError = null,
                mealType = state.mealType ?: mealType?.lowercase()?.takeIf { it in MEAL_TYPES },
            )
        }
        try {
            val recipe = repository.getRecipe(recipeId)
            _state.update { it.copy(recipe = recipe, isLoading = false) }
        } catch (e: CancellationException) {
            _state.update { it.copy(isLoading = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(isLoading = false, loadError = e.toAddMealError()) }
            return
        }
        loadDays(planId)
    }

    private suspend fun loadDays(planId: String) {
        if (_state.value.days.isNotEmpty()) return
        try {
            val plan = repository.getMealPlan(planId)
            _state.update { it.copy(days = planDays(plan.startDate, plan.endDate)) }
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught", "SwallowedException") e: Exception) {
            // Not fatal: without the plan's days the meal is simply added without a day.
        }
    }
    fun onMealTypeChange(value: String) {
        if (_state.value.addedMealId != null) return
        _state.update {
            it.copy(mealType = value.takeIf { type -> type in MEAL_TYPES }, mealTypeError = null, error = null)
        }
    }

    fun onServingsChange(value: String) {
        if (_state.value.addedMealId != null) return
        _state.update { it.copy(servings = value.decimalOnly(), servingsError = null, error = null) }
    }

    /** Choose the day of the plan (0-based), or null for no day. */
    fun onDayChange(dayIndex: Int?) {
        _state.update { state ->
            state.copy(
                dayIndex = dayIndex?.takeIf { index -> state.days.any { it.dayIndex == index } },
                // Once the meal exists the error is about setting its day: keep it so the retry stays offered.
                error = if (state.addedMealId != null) state.error else null,
            )
        }
    }

    /** Add the meal (and place it on the chosen day). Does nothing while saving or once finished. */
    suspend fun save() {
        val current = _state.value
        if (current.isSaving || current.isDone) return
        val planId = planId ?: return
        val recipeId = recipeId ?: return

        var servings = 0.0
        if (current.addedMealId == null) {
            val mealTypeError = if (current.mealType == null) AddMealFieldError.MEAL_TYPE_REQUIRED else null
            val servingsError = servingsError(current.servings)
            if (mealTypeError != null || servingsError != null) {
                _state.update { it.copy(mealTypeError = mealTypeError, servingsError = servingsError) }
                return
            }
            servings = current.servings.toDouble()
        }

        _state.update { it.copy(isSaving = true, error = null) }
        try {
            val mealId = current.addedMealId ?: repository.addMeal(
                planId,
                AddMealRequest(mealType = current.mealType!!, recipeId = recipeId, servings = servings),
            ).id.also { id -> _state.update { it.copy(addedMealId = id) } }

            current.dayIndex?.let { day ->
                repository.updateMeal(planId, mealId, UpdateMealRequest(dayIndex = day))
            }
            _state.update { it.copy(isSaving = false, isDone = true) }
        } catch (e: CancellationException) {
            _state.update { it.copy(isSaving = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            if (queueInstead(e, planId, recipeId, servings)) return
            _state.update { it.copy(isSaving = false, error = e.toAddMealError()) }
        }
    }

    /**
     * When the server could not be reached for the add itself, save the meal on the device so the
     * form can finish now and the meal is sent later. Returns whether it did.
     */
    private fun queueInstead(e: Exception, planId: String, recipeId: String, servings: Double): Boolean {
        val state = _state.value
        val recipe = state.recipe
        val mealType = state.mealType
        val canQueue = sync != null && recipe != null && mealType != null &&
            // Only the add itself: once the server created the meal, a retry just sets its day.
            state.addedMealId == null &&
            e.toApiFailure().let { it == ApiFailure.OFFLINE || it == ApiFailure.SERVER }
        if (!canQueue) return false
        sync!!.queueAdd(
            planId = planId,
            request = AddMealRequest(mealType = mealType!!, recipeId = recipeId, servings = servings),
            dayIndex = state.dayIndex,
            recipe = recipe!!,
        )
        _state.update { it.copy(isSaving = false, queued = true, isDone = true) }
        return true
    }

    private fun servingsError(text: String): AddMealFieldError? {
        if (text.isBlank()) return AddMealFieldError.SERVINGS_REQUIRED
        val value = text.toDoubleOrNull() ?: return AddMealFieldError.SERVINGS_INVALID
        return if (value <= 0.0 || value > MAX_SERVINGS) AddMealFieldError.SERVINGS_INVALID else null
    }

    companion object {
        /** The meal types the API accepts. */
        val MEAL_TYPES = listOf("breakfast", "lunch", "dinner", "snack")

        private const val MAX_SERVINGS = 99.0
    }
}

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
