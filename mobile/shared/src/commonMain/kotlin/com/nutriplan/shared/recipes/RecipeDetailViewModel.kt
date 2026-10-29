package com.nutriplan.shared.recipes

import com.nutriplan.shared.data.model.NutritionDisclaimer
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.toApiFailure
import com.nutriplan.shared.data.repository.DietaryRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/** Why a recipe could not be loaded. Locale-neutral: each platform maps these to its own copy. */
enum class RecipeDetailError {
    /** The device could not reach the server. */
    NETWORK,

    /** The server failed (HTTP 5xx). */
    SERVER_PROBLEM,

    /** The recipe does not exist (any more), or the link was stale. */
    NOT_FOUND,

    /** The server rejected the session (HTTP 401): the user has to sign in again. */
    SESSION_EXPIRED,

    /** Anything else. */
    UNKNOWN,
}

/**
 * Observable state of the recipe detail (DPL-603).
 *
 * [disclaimer] is the catalog's nutrition disclaimer from the server. It is loaded after the recipe
 * and may be null if that request failed; the screen then shows its own bundled disclaimer, because
 * nutrition values must never be shown without one.
 */
data class RecipeDetailUiState(
    val recipe: Recipe? = null,
    val disclaimer: NutritionDisclaimer? = null,
    val isLoading: Boolean = true,
    val error: RecipeDetailError? = null,
)

/** Maps a thrown repository failure to a stable, localizable [RecipeDetailError]. */
fun Throwable.toRecipeDetailError(): RecipeDetailError = when (toApiFailure()) {
    ApiFailure.OFFLINE -> RecipeDetailError.NETWORK
    ApiFailure.SERVER -> RecipeDetailError.SERVER_PROBLEM
    ApiFailure.SESSION_EXPIRED -> RecipeDetailError.SESSION_EXPIRED
    ApiFailure.NOT_FOUND -> RecipeDetailError.NOT_FOUND
    else -> RecipeDetailError.UNKNOWN
}

/**
 * Shared logic of the recipe detail used by the Compose (DPL-603) and SwiftUI screens.
 *
 * The functions are `suspend` so the UI owns the coroutine scope; [CancellationException] is
 * rethrown so leaving the screen cancels cleanly.
 */
class RecipeDetailViewModel(
    private val repository: DietaryRepository,
) {

    private val _state = MutableStateFlow(RecipeDetailUiState())
    val state: StateFlow<RecipeDetailUiState> = _state.asStateFlow()

    /** The current UI state, for callers that read rather than observe it (e.g. the SwiftUI bridge). */
    fun currentState(): RecipeDetailUiState = _state.value

    /** Load [recipeId] and the nutrition disclaimer; also the retry after a failure. */
    suspend fun load(recipeId: String) {
        _state.update { it.copy(isLoading = it.recipe == null, error = null) }
        try {
            val recipe = repository.getRecipe(recipeId)
            _state.update { it.copy(recipe = recipe, isLoading = false) }
        } catch (e: CancellationException) {
            _state.update { it.copy(isLoading = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(isLoading = false, error = e.toRecipeDetailError()) }
            return
        }
        loadDisclaimer()
    }

    private suspend fun loadDisclaimer() {
        if (_state.value.disclaimer != null) return
        try {
            val disclaimer = repository.getNutritionDisclaimer()
            _state.update { it.copy(disclaimer = disclaimer) }
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught", "SwallowedException") e: Exception) {
            // Not fatal: the screen falls back to its bundled disclaimer.
        }
    }
}
