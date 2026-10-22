package com.nutriplan.shared.ai

import com.nutriplan.shared.data.model.AiRecommendations
import com.nutriplan.shared.data.model.DietaryPreferences
import com.nutriplan.shared.recipes.splitToIngredients
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/**
 * Observable state of the AI recommendations screen (AIA-602).
 *
 * [mealType] and [ingredients] are what the user asks for (the raw text of the field for the
 * ingredients); [result] is the answer to the last request that finished, with its reasoning,
 * alignment and the medical disclaimer the screen must show with it.
 */
data class AiRecommendationsUiState(
    /** One of [AiRecommendationsViewModel.MEAL_TYPES], or null for a whole day. */
    val mealType: String? = null,
    /** Ingredients on hand, separated by commas. */
    val ingredients: String = "",
    val isLoading: Boolean = false,
    val result: AiRecommendations? = null,
    /** The meal type [result] was asked for (null for a whole day), used when adding one to a plan. */
    val resultMealType: String? = null,
    val error: AiError? = null,
    val hasRequested: Boolean = false,
) {
    /** A request finished without error and recommended nothing. */
    val isEmpty: Boolean
        get() = hasRequested && !isLoading && error == null && result?.recommendations.isNullOrEmpty()
}

/**
 * Shared logic of the AI recommendations screen (AIA-602), used by the Compose and SwiftUI screens.
 *
 * - [recommend] asks the AI Advisor for recipes that fit the user's saved dietary preferences
 *   ([preferences]), for the chosen meal type and the ingredients on hand.
 * - A newer request makes an older one irrelevant: its answer is dropped, so a slow reply never
 *   replaces a fresher one.
 * - A failed request clears the previous answer instead of showing it next to the error.
 *
 * The functions are `suspend` so the UI owns the coroutine scope; [CancellationException] is
 * rethrown so leaving the screen cancels cleanly.
 */
class AiRecommendationsViewModel(
    private val advisor: AiAdvisor,
    private val preferences: () -> DietaryPreferences?,
) {

    private val _state = MutableStateFlow(AiRecommendationsUiState())
    val state: StateFlow<AiRecommendationsUiState> = _state.asStateFlow()

    /** Identifies the latest request; answers to older ones are ignored. */
    private var generation = 0

    /** Choose a meal type, or null for recommendations across a whole day. */
    fun onMealTypeChange(value: String?) {
        _state.update { it.copy(mealType = value?.takeIf { type -> type in MEAL_TYPES }) }
    }

    fun onIngredientsChange(value: String) {
        _state.update { it.copy(ingredients = value) }
    }

    /** Ask for recommendations with what is set now; also the retry after a failure. */
    suspend fun recommend() {
        val token = ++generation
        val request = _state.value
        _state.update { it.copy(isLoading = true, error = null) }
        try {
            val outcome = advisor.recommend(
                preferences = preferences(),
                mealType = request.mealType,
                availableIngredients = request.ingredients.splitToIngredients(),
            )
            if (token != generation) return
            _state.update { state ->
                when (outcome) {
                    is AiResult.Success -> state.copy(
                        result = outcome.value,
                        resultMealType = request.mealType,
                        isLoading = false,
                        hasRequested = true,
                    )
                    is AiResult.Failure -> state.copy(
                        result = null,
                        resultMealType = null,
                        isLoading = false,
                        hasRequested = true,
                        error = outcome.error,
                    )
                }
            }
        } catch (e: CancellationException) {
            if (token == generation) _state.update { it.copy(isLoading = false) }
            throw e
        }
    }

    companion object {
        /** The meal types a recommendation can be for. */
        val MEAL_TYPES = listOf("breakfast", "lunch", "dinner", "snack")
    }
}
