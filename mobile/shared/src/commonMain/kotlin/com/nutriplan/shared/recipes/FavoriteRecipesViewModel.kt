package com.nutriplan.shared.recipes

import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.toApiFailure
import com.nutriplan.shared.data.repository.FavoriteRecipesRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/** Why favorites could not be loaded or changed. Locale-neutral: each platform maps these to its own copy. */
enum class FavoriteError {
    /** The device could not reach the server. Favorites cannot be changed offline (yet). */
    NETWORK,

    /** The server failed (HTTP 5xx). */
    SERVER_PROBLEM,

    /** The server rejected the session (HTTP 401): the user has to sign in again. */
    SESSION_EXPIRED,

    /** Anything else. */
    UNKNOWN,
}

/**
 * Observable state of the user's favorite recipes (DPL-607), shared by the favorites list and by
 * every heart on the recipe screens.
 *
 * [recipes] is the favorites list, most recently saved first. [pendingIds] are recipes whose change
 * is being sent to the server. [loadError] is why the list could not be loaded; [changeError] is why
 * the last heart toggle was undone.
 */
data class FavoriteRecipesUiState(
    val recipes: List<Recipe> = emptyList(),
    /** The list was loaded (from the server or the device) at least once. */
    val hasLoaded: Boolean = false,
    val isLoading: Boolean = false,
    /** The server could not be reached, so [recipes] is the copy saved on the device. */
    val isOffline: Boolean = false,
    val pendingIds: Set<String> = emptySet(),
    val loadError: FavoriteError? = null,
    val changeError: FavoriteError? = null,
) {
    /** The ids of the favorite recipes. */
    val ids: Set<String> get() = recipes.mapTo(HashSet()) { it.id }

    fun isFavorite(recipeId: String): Boolean = recipes.any { it.id == recipeId }
}

/** Maps a thrown repository failure to a stable, localizable [FavoriteError]. */
fun Throwable.toFavoriteError(): FavoriteError = when (toApiFailure()) {
    ApiFailure.OFFLINE -> FavoriteError.NETWORK
    ApiFailure.SERVER -> FavoriteError.SERVER_PROBLEM
    ApiFailure.SESSION_EXPIRED -> FavoriteError.SESSION_EXPIRED
    else -> FavoriteError.UNKNOWN
}

/**
 * Shared logic of favorite recipes used by the Compose and SwiftUI screens. One instance serves the
 * whole app, so a heart toggled on the recipe page is already filled in the search results.
 *
 * - [load] reads the favorites (from the device when the server cannot be reached).
 * - [toggle] flips a recipe's heart **immediately** and sends the change; if the server refuses (or
 *   cannot be reached) the heart goes back and [FavoriteRecipesUiState.changeError] says why. A
 *   recipe whose change is still in flight ignores further taps.
 * - [reset] forgets everything (on sign-out).
 *
 * The functions are `suspend` so the UI owns the coroutine scope; [CancellationException] is
 * rethrown, after putting the heart back, so leaving a screen cancels cleanly.
 */
class FavoriteRecipesViewModel(
    private val repository: FavoriteRecipesRepository,
) {

    private val _state = MutableStateFlow(FavoriteRecipesUiState())
    val state: StateFlow<FavoriteRecipesUiState> = _state.asStateFlow()

    /** Load the favorites; also the retry after a failure. Keeps what is shown while loading. */
    suspend fun load() {
        _state.update { it.copy(isLoading = true, loadError = null) }
        try {
            val favorites = repository.load()
            _state.update {
                it.copy(
                    recipes = favorites.recipes,
                    hasLoaded = true,
                    isLoading = false,
                    isOffline = favorites.fromCache,
                )
            }
        } catch (e: CancellationException) {
            _state.update { it.copy(isLoading = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(isLoading = false, loadError = e.toFavoriteError()) }
        }
    }

    /** Flip [recipe]'s heart: save it if it is not a favorite, remove it if it is. */
    suspend fun toggle(recipe: Recipe) {
        val before = _state.value
        if (recipe.id in before.pendingIds) return
        val wasFavorite = before.isFavorite(recipe.id)
        val oldIndex = before.recipes.indexOfFirst { it.id == recipe.id }

        _state.update { state ->
            state.copy(
                recipes = if (wasFavorite) state.recipes.filter { it.id != recipe.id } else listOf(recipe) + state.recipes,
                pendingIds = state.pendingIds + recipe.id,
                changeError = null,
            )
        }
        try {
            if (wasFavorite) repository.remove(recipe.id) else repository.add(recipe)
            _state.update { it.copy(pendingIds = it.pendingIds - recipe.id) }
        } catch (e: CancellationException) {
            undo(recipe, wasFavorite, oldIndex, error = null)
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            undo(recipe, wasFavorite, oldIndex, error = e.toFavoriteError())
        }
    }

    /** Dismiss the message about an undone change. */
    fun clearChangeError() {
        _state.update { it.copy(changeError = null) }
    }

    /** Forget every favorite, in memory and on the device (on sign-out). */
    fun reset() {
        _state.value = FavoriteRecipesUiState()
        repository.clearCache()
    }

    /** Put [recipe]'s heart back the way it was before the failed change. */
    private fun undo(recipe: Recipe, wasFavorite: Boolean, oldIndex: Int, error: FavoriteError?) {
        _state.update { state ->
            val recipes = if (wasFavorite) {
                if (state.recipes.any { it.id == recipe.id }) {
                    state.recipes
                } else {
                    state.recipes.toMutableList().apply { add(oldIndex.coerceIn(0, size), recipe) }
                }
            } else {
                state.recipes.filter { it.id != recipe.id }
            }
            state.copy(
                recipes = recipes,
                pendingIds = state.pendingIds - recipe.id,
                changeError = error ?: state.changeError,
            )
        }
    }
}
