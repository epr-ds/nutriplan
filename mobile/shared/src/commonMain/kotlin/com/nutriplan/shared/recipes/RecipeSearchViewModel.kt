package com.nutriplan.shared.recipes

import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.model.RecipeSearchQuery
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.toApiFailure
import com.nutriplan.shared.data.repository.DietaryRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/** Why recipes could not be loaded. Locale-neutral: each platform maps these to its own copy. */
enum class RecipeListError {
    /** The device could not reach the server. Recipes are not stored on the device (yet). */
    NETWORK,

    /** The server failed (HTTP 5xx). */
    SERVER_PROBLEM,

    /** The server rejected the session (HTTP 401): the user has to sign in again. */
    SESSION_EXPIRED,

    /** Anything else. */
    UNKNOWN,
}

/**
 * Observable state of the recipe search (DPL-601).
 *
 * The filter fields hold the raw text the user typed; [recipes] are the results of the last
 * [RecipeSearchViewModel.search], so editing a filter does not change the list until it is applied.
 */
data class RecipeSearchUiState(
    /** Ingredients to look for, separated by commas. */
    val ingredients: String = "",
    /** One of [RecipeSearchViewModel.DIET_TYPES], or null for any. */
    val dietType: String? = null,
    val maxCalories: String = "",
    val minProtein: String = "",
    val recipes: List<Recipe> = emptyList(),
    val isLoading: Boolean = false,
    val isLoadingMore: Boolean = false,
    /** The last page was full, so another page may exist. */
    val hasMore: Boolean = false,
    val hasSearched: Boolean = false,
    val error: RecipeListError? = null,
) {
    /** A search finished without error and found nothing. */
    val isEmptyResult: Boolean get() = hasSearched && !isLoading && error == null && recipes.isEmpty()

    /** Whether any filter is set. */
    val hasFilters: Boolean
        get() = ingredients.isNotBlank() || dietType != null || maxCalories.isNotBlank() || minProtein.isNotBlank()
}

/** Maps a thrown repository failure to a stable, localizable [RecipeListError]. */
fun Throwable.toRecipeListError(): RecipeListError = when (toApiFailure()) {
    ApiFailure.OFFLINE -> RecipeListError.NETWORK
    ApiFailure.SERVER -> RecipeListError.SERVER_PROBLEM
    ApiFailure.SESSION_EXPIRED -> RecipeListError.SESSION_EXPIRED
    else -> RecipeListError.UNKNOWN
}

/**
 * Shared logic of the recipe search used by the Compose (DPL-601) and SwiftUI screens.
 *
 * - [search] runs the current filters from the first page; [loadMore] appends the next page of the
 *   *last executed* search (not of filters edited since).
 * - A newer search makes any older request's result irrelevant: it is dropped, so a slow response
 *   can never overwrite fresher results.
 * - Number fields only ever hold digits (and one decimal point for protein).
 *
 * The functions are `suspend` so the UI owns the coroutine scope; [CancellationException] is
 * rethrown so leaving the screen cancels cleanly.
 */
class RecipeSearchViewModel(
    private val repository: DietaryRepository,
) {

    private val _state = MutableStateFlow(RecipeSearchUiState())
    val state: StateFlow<RecipeSearchUiState> = _state.asStateFlow()

    /** Identifies the latest search; results of older requests are ignored. */
    private var generation = 0
    private var lastQuery = RecipeSearchQuery()
    private var nextPage = 1

    fun onIngredientsChange(value: String) {
        _state.update { it.copy(ingredients = value) }
    }

    fun onDietTypeChange(value: String?) {
        _state.update { it.copy(dietType = value?.takeIf { type -> type in DIET_TYPES }) }
    }

    fun onMaxCaloriesChange(value: String) {
        _state.update { it.copy(maxCalories = value.filter(Char::isDigit).take(MAX_NUMBER_DIGITS)) }
    }

    fun onMinProteinChange(value: String) {
        _state.update { it.copy(minProtein = value.decimalOnly()) }
    }

    /** Clear every filter. Results stay until the next [search]. */
    fun clearFilters() {
        _state.update { it.copy(ingredients = "", dietType = null, maxCalories = "", minProtein = "") }
    }

    /** Search with the current filters from the first page, replacing the results. */
    suspend fun search() {
        val token = ++generation
        val query = currentQuery()
        lastQuery = query
        _state.update { it.copy(isLoading = true, isLoadingMore = false, error = null) }
        try {
            val recipes = repository.searchRecipes(query)
            if (token != generation) return
            nextPage = query.page + 1
            _state.update {
                it.copy(
                    recipes = recipes,
                    isLoading = false,
                    hasMore = recipes.size >= query.limit,
                    hasSearched = true,
                )
            }
        } catch (e: CancellationException) {
            if (token == generation) _state.update { it.copy(isLoading = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            if (token != generation) return
            // Results of the previous filters would be misleading next to an error, so drop them.
            _state.update {
                it.copy(
                    recipes = emptyList(),
                    isLoading = false,
                    hasMore = false,
                    hasSearched = true,
                    error = e.toRecipeListError(),
                )
            }
        }
    }

    /** Append the next page of the last search. Does nothing while loading or when there is no more. */
    suspend fun loadMore() {
        val current = _state.value
        if (!current.hasMore || current.isLoading || current.isLoadingMore) return

        val token = generation
        _state.update { it.copy(isLoadingMore = true, error = null) }
        try {
            val page = repository.searchRecipes(lastQuery.copy(page = nextPage))
            if (token != generation) return
            nextPage++
            _state.update { state ->
                val known = state.recipes.mapTo(HashSet()) { it.id }
                state.copy(
                    recipes = state.recipes + page.filter { it.id !in known },
                    isLoadingMore = false,
                    hasMore = page.size >= lastQuery.limit,
                )
            }
        } catch (e: CancellationException) {
            if (token == generation) _state.update { it.copy(isLoadingMore = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            if (token != generation) return
            // Keep what is shown (and hasMore, so the user can try again).
            _state.update { it.copy(isLoadingMore = false, error = e.toRecipeListError()) }
        }
    }

    private fun currentQuery(): RecipeSearchQuery {
        val s = _state.value
        return RecipeSearchQuery(
            ingredients = s.ingredients.splitToIngredients(),
            dietType = s.dietType,
            maxCalories = s.maxCalories.toIntOrNull(),
            minProtein = s.minProtein.toDoubleOrNull(),
        )
    }

    companion object {
        /** The diet types the catalog can be filtered by (`dietType` in the contract). */
        val DIET_TYPES = listOf("omnivore", "vegetarian", "vegan", "keto", "paleo")

        private const val MAX_NUMBER_DIGITS = 5
    }
}

/** "chicken, olive oil;rice" -> [chicken, olive oil, rice]: trimmed, no blanks, no repeats. */
internal fun String.splitToIngredients(): List<String> =
    split(',', ';', '\n')
        .map { it.trim() }
        .filter { it.isNotEmpty() }
        .distinctBy { it.lowercase() }

/** Keeps digits and at most one decimal point, limited in length. */
private fun String.decimalOnly(): String {
    var seenDot = false
    return filter { c ->
        when {
            c.isDigit() -> true
            c == '.' && !seenDot -> true.also { seenDot = true }
            else -> false
        }
    }.take(8)
}
