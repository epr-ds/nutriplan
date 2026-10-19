package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.DietaryPreferences
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.toApiFailure
import com.nutriplan.shared.data.repository.DietaryRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/** A problem with one field of the plan form, shown inline. Locale-neutral (IDN-902 convention). */
enum class PlanFieldError {
    NAME_REQUIRED,
    START_DATE_REQUIRED,
    END_DATE_REQUIRED,
    END_BEFORE_START,
    CALORIES_REQUIRED,
    CALORIES_INVALID,
}

/** Why a plan could not be saved, shown for the whole form. */
enum class MealPlanFormError {
    /** The device could not reach the server. Plans cannot be created offline. */
    NETWORK,

    /** The server failed (HTTP 5xx). */
    SERVER_PROBLEM,

    /** The server rejected the session (HTTP 401): the user has to sign in again. */
    SESSION_EXPIRED,

    /** The server refused the content (HTTP 400/422) although the app's own checks passed. */
    REJECTED,

    /** Anything else. */
    UNKNOWN,
}

/**
 * Observable state of the create-plan form (DPL-503).
 *
 * Dates are ISO strings (`yyyy-MM-dd`); [calories] is the raw text of the field so a half-typed
 * number is never lost. [createdPlanId] is set once the server created the plan, which tells the
 * screen to open it.
 */
data class MealPlanFormUiState(
    val name: String = "",
    val startDate: String = "",
    val endDate: String = "",
    val calories: String = "",
    val nameError: PlanFieldError? = null,
    val startDateError: PlanFieldError? = null,
    val endDateError: PlanFieldError? = null,
    val caloriesError: PlanFieldError? = null,
    /** The calorie target came from the user's dietary preferences and has not been edited. */
    val caloriesPrefilled: Boolean = false,
    val isSaving: Boolean = false,
    val error: MealPlanFormError? = null,
    val createdPlanId: String? = null,
)

/**
 * Shared logic of the create-plan form used by the Compose (DPL-503) and SwiftUI screens.
 *
 * - [start] fills sensible defaults: a week starting today, and the daily calorie target (plus the
 *   diet type and macro targets sent with the request) from the user's dietary preferences.
 * - The checks mirror the server's rules: a name, valid dates, an end date that is not before the
 *   start date, and a daily calorie target (the API requires one).
 * - Plans cannot be created offline; the form says so instead of queueing something it cannot send.
 *
 * The functions are `suspend` where they call the server so the UI owns the coroutine scope;
 * [CancellationException] is rethrown so leaving the screen cancels cleanly.
 *
 * @param preferences the signed-in user's dietary preferences, if known.
 */
class MealPlanFormViewModel(
    private val repository: DietaryRepository,
    private val preferences: () -> DietaryPreferences?,
) {

    private val _state = MutableStateFlow(MealPlanFormUiState())
    val state: StateFlow<MealPlanFormUiState> = _state.asStateFlow()

    /** Fill the defaults. [today] is the device's local date (ISO), which only the platform knows. */
    fun start(today: String) {
        val prefs = preferences()
        val target = prefs?.dailyCalorieTarget?.takeIf { it > 0 }
        _state.update {
            it.copy(
                startDate = today,
                endDate = IsoDate.addDays(today, DEFAULT_PLAN_DAYS - 1).orEmpty(),
                calories = target?.toString().orEmpty(),
                caloriesPrefilled = target != null,
            )
        }
    }

    fun onNameChange(value: String) {
        _state.update { it.copy(name = value, nameError = null, error = null) }
    }

    /**
     * Change the start date. If the end date would then be before it, the end date moves along so
     * the plan keeps its length (a week by default).
     */
    fun onStartDateChange(value: String) {
        _state.update { current ->
            val span = IsoDate.daysBetween(current.startDate, current.endDate)?.takeIf { it >= 0 } ?: (DEFAULT_PLAN_DAYS - 1)
            val endBeforeStart = IsoDate.daysBetween(value, current.endDate)?.let { it < 0 } ?: true
            current.copy(
                startDate = value,
                endDate = if (endBeforeStart) IsoDate.addDays(value, span).orEmpty() else current.endDate,
                startDateError = null,
                endDateError = null,
                error = null,
            )
        }
    }

    fun onEndDateChange(value: String) {
        _state.update { it.copy(endDate = value, endDateError = null, error = null) }
    }

    /** Only digits are kept, so the field can never hold something that is not a whole number. */
    fun onCaloriesChange(value: String) {
        _state.update {
            it.copy(
                calories = value.filter(Char::isDigit).take(MAX_CALORIE_DIGITS),
                caloriesError = null,
                caloriesPrefilled = false,
                error = null,
            )
        }
    }

    /** Checks every field, setting the inline errors. Returns true when the form can be saved. */
    fun validate(): Boolean {
        val current = _state.value
        val nameError = if (current.name.isBlank()) PlanFieldError.NAME_REQUIRED else null
        val startError = when {
            current.startDate.isBlank() || !IsoDate.isValid(current.startDate) -> PlanFieldError.START_DATE_REQUIRED
            else -> null
        }
        val endError = when {
            current.endDate.isBlank() || !IsoDate.isValid(current.endDate) -> PlanFieldError.END_DATE_REQUIRED
            startError == null && (IsoDate.daysBetween(current.startDate, current.endDate) ?: 0) < 0 ->
                PlanFieldError.END_BEFORE_START
            else -> null
        }
        val calories = current.calories.toIntOrNull()
        val caloriesError = when {
            current.calories.isBlank() -> PlanFieldError.CALORIES_REQUIRED
            calories == null || calories <= 0 -> PlanFieldError.CALORIES_INVALID
            else -> null
        }
        _state.update {
            it.copy(
                nameError = nameError,
                startDateError = startError,
                endDateError = endError,
                caloriesError = caloriesError,
            )
        }
        return listOf(nameError, startError, endError, caloriesError).all { it == null }
    }

    /**
     * Creates the plan. Returns true on success (then [MealPlanFormUiState.createdPlanId] is set);
     * false on a failed check or a failed request (then the field errors or
     * [MealPlanFormUiState.error] say why). A second call while one is running does nothing.
     */
    suspend fun save(): Boolean {
        if (_state.value.isSaving || !validate()) return false

        val current = _state.value
        val prefs = preferences()
        _state.update { it.copy(isSaving = true, error = null) }
        return try {
            val plan = repository.createMealPlan(
                CreateMealPlanRequest(
                    name = current.name.trim(),
                    startDate = current.startDate,
                    endDate = current.endDate,
                    dailyCalorieTarget = current.calories.toInt(),
                    macroTargets = prefs?.macroTargets,
                    dietaryType = prefs?.dietType?.lowercase()?.takeIf { it in PLAN_DIET_TYPES },
                ),
            )
            _state.update { it.copy(isSaving = false, createdPlanId = plan.id) }
            true
        } catch (e: CancellationException) {
            _state.update { it.copy(isSaving = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(isSaving = false, error = e.toMealPlanFormError()) }
            false
        }
    }

    private companion object {
        const val DEFAULT_PLAN_DAYS = 7
        const val MAX_CALORIE_DIGITS = 6

        /** The diet types a plan accepts (`CreateMealPlanRequest.dietaryType`); preferences allow more. */
        val PLAN_DIET_TYPES = setOf("omnivore", "vegetarian", "vegan", "keto", "paleo")
    }
}

/** Maps a thrown repository failure to a stable, localizable [MealPlanFormError]. */
fun Throwable.toMealPlanFormError(): MealPlanFormError = when (toApiFailure()) {
    ApiFailure.OFFLINE -> MealPlanFormError.NETWORK
    ApiFailure.SERVER -> MealPlanFormError.SERVER_PROBLEM
    ApiFailure.SESSION_EXPIRED -> MealPlanFormError.SESSION_EXPIRED
    ApiFailure.REJECTED -> MealPlanFormError.REJECTED
    else -> MealPlanFormError.UNKNOWN
}
