package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.local.FavoriteRecipeCache
import com.nutriplan.shared.data.local.PendingFavoriteStore
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.toApiFailure
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
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
 * - [load] first sends any queued toggles, then reads every page from the server and replaces the
 *   cache with the result. When the device is offline or the server answers with a 5xx error it
 *   returns the cached copy instead, marked [FavoriteRecipes.fromCache]; any other failure (such as
 *   a rejected session) is rethrown. Either way, toggles still waiting to be sent are applied on top
 *   (the server's list wins, the waiting toggles are the later writes).
 * - [add] and [remove] go to the server first and update the cache only after it agreed. With a
 *   [pending] queue (DPL-407), a toggle the server cannot be reached for (offline or a 5xx) is
 *   queued instead of failing, the platform is asked to sync, and it is sent later; the API's PUT
 *   and DELETE are idempotent, so replaying it is safe.
 */
class FavoriteRecipesRepository(
    private val remote: FavoriteRecipesRemote,
    private val cache: FavoriteRecipeCache,
    private val pending: PendingFavoriteStore? = null,
    private val scheduler: SyncScheduler = SyncScheduler.None,
) {

    private val flushing = Mutex()

    suspend fun load(): FavoriteRecipes {
        runCatching { flushPending() }.onFailure { if (it is CancellationException) throw it }
        val recipes = try {
            readAllPages()
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            if (!e.canFallBackToCache()) throw e
            return FavoriteRecipes(cache.getAll().withPendingToggles(), fromCache = true)
        }
        cache.replaceAll(recipes)
        return FavoriteRecipes(recipes.withPendingToggles(), fromCache = false)
    }

    /** Save [recipe] as a favorite (queued when the server cannot be reached and a queue exists). */
    suspend fun add(recipe: Recipe) {
        if (sendOrQueue(recipe, favorite = true) { remote.add(recipe.id) }) cache.addFirst(recipe)
    }

    /** Remove [recipe] from the favorites (queued like [add]). */
    suspend fun remove(recipe: Recipe) {
        if (sendOrQueue(recipe, favorite = false) { remote.remove(recipe.id) }) cache.remove(recipe.id)
    }

    /**
     * Send the queued toggles, oldest first. One the server cannot be reached for stays queued and
     * stops the run; one it will never accept (for example a recipe that left the catalog) is
     * dropped, and the next load shows the server's list.
     */
    suspend fun flushPending(): FlushResult = flushing.withLock {
        val queue = pending ?: return@withLock FlushResult(0, 0, 0)
        var sent = 0
        var dropped = 0
        for (wish in queue.waiting()) {
            try {
                if (wish.favorite) remote.add(wish.recipe.id) else remote.remove(wish.recipe.id)
                if (wish.favorite) cache.addFirst(wish.recipe) else cache.remove(wish.recipe.id)
                queue.remove(wish.recipe.id)
                sent++
            } catch (e: CancellationException) {
                throw e
            } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
                if (e.isTemporary()) {
                    queue.bumpAttempts(wish.recipe.id)
                    return@withLock FlushResult(sent, dropped, waiting = queue.waiting().size)
                }
                queue.remove(wish.recipe.id)
                dropped++
            }
        }
        FlushResult(sent, dropped, waiting = 0)
    }

    /** Forget the saved copy and the queued toggles (for example on logout). */
    fun clearCache() {
        cache.clear()
        pending?.clear()
    }

    /** Send now; if the server cannot be reached and there is a queue, queue it. Returns whether it was sent. */
    private suspend fun sendOrQueue(recipe: Recipe, favorite: Boolean, send: suspend () -> Unit): Boolean {
        try {
            send()
            // A newer wish that reached the server replaces any older queued one for this recipe.
            pending?.remove(recipe.id)
            return true
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            val queue = pending
            if (queue == null || !e.canFallBackToCache()) throw e
            queue.queue(recipe, favorite)
            scheduler.requestSync()
            return false
        }
    }

    private fun List<Recipe>.withPendingToggles(): List<Recipe> {
        val wishes = pending?.waiting().orEmpty()
        if (wishes.isEmpty()) return this
        val removed = wishes.filter { !it.favorite }.mapTo(HashSet()) { it.recipe.id }
        val kept = filter { it.id !in removed }
        val added = wishes.filter { it.favorite && kept.none { r -> r.id == it.recipe.id } }.map { it.recipe }.reversed()
        return added + kept
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

    private fun Throwable.isTemporary(): Boolean =
        toApiFailure().let { it == ApiFailure.OFFLINE || it == ApiFailure.SERVER || it == ApiFailure.SESSION_EXPIRED }

    private companion object {
        /** A safety bound: 1,000 favorites is far beyond what a person saves. */
        const val MAX_PAGES = 10
    }
}

/** Sends both offline queues (meals and favorites): what the platform's background job runs. */
class CombinedQueueFlusher(
    private val meals: MealQueueFlusher,
    private val favorites: FavoriteRecipesRepository,
) : MealQueueFlusher {
    override suspend fun flush(): FlushResult {
        val a = meals.flush()
        val b = favorites.flushPending()
        return FlushResult(added = a.added + b.added, failed = a.failed + b.failed, waiting = a.waiting + b.waiting)
    }
}
