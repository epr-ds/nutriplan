package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.local.FavoriteRecipeCache
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.toApiFailure
import kotlin.coroutines.cancellation.CancellationException

/** The user's favorite recipes and where they came from. */
data class FavoriteRecipes(
    /** Most recently saved first. */
    val recipes: List<Recipe>,
    /** The server could not be reached, so [recipes] is the copy saved on the device. */
    val fromCache: Boolean,
)

/**
 * Favorite recipes (DPL-607): the server is the source of truth and a local [FavoriteRecipeCache]
 * keeps a copy for when it cannot be reached.
 *
 * - [load] reads every page from the server and replaces the cache with the result. When the device
 *   is offline or the server answers with a 5xx error it returns the cached copy instead, marked
 *   [FavoriteRecipes.fromCache]; any other failure (such as a rejected session) is rethrown.
 * - [add] and [remove] go to the server first and update the cache only after it agreed, so the copy
 *   never claims something the server does not have. They need a connection (queued offline changes
 *   are DPL-407).
 */
class FavoriteRecipesRepository(
    private val remote: FavoriteRecipesRemote,
    private val cache: FavoriteRecipeCache,
) {

    suspend fun load(): FavoriteRecipes {
        val recipes = try {
            readAllPages()
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            if (!e.canFallBackToCache()) throw e
            return FavoriteRecipes(cache.getAll(), fromCache = true)
        }
        cache.replaceAll(recipes)
        return FavoriteRecipes(recipes, fromCache = false)
    }

    /** Save [recipe] as a favorite. */
    suspend fun add(recipe: Recipe) {
        remote.add(recipe.id)
        cache.addFirst(recipe)
    }

    /** Remove the favorite with [recipeId]. */
    suspend fun remove(recipeId: String) {
        remote.remove(recipeId)
        cache.remove(recipeId)
    }

    /** Forget the saved copy (for example on logout). */
    fun clearCache() {
        cache.clear()
    }

    private suspend fun readAllPages(): List<Recipe> {
        val all = mutableListOf<Recipe>()
        for (page in 1..MAX_PAGES) {
            val batch = remote.list(page = page, limit = FavoriteRecipesRemote.DEFAULT_LIMIT)
            all += batch
            if (batch.size < FavoriteRecipesRemote.DEFAULT_LIMIT) break
        }
        // A recipe repeated across pages (saved while paging) is listed once.
        return all.distinctBy { it.id }
    }

    private fun Throwable.canFallBackToCache(): Boolean =
        toApiFailure().let { it == ApiFailure.OFFLINE || it == ApiFailure.SERVER }

    private companion object {
        /** A safety bound: 1,000 favorites is far beyond what a person saves. */
        const val MAX_PAGES = 10
    }
}
