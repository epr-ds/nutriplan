package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.local.FavoriteRecipeCache
import com.nutriplan.shared.data.local.PendingFavoriteStore
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.recipes.FavoriteRecipesViewModel
import com.nutriplan.shared.testing.FakeFavoriteRemote
import com.nutriplan.shared.testing.RecordingScheduler
import com.nutriplan.shared.testing.favoriteRecipe
import com.nutriplan.shared.testing.newDatabase
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** DPL-407: favorite toggles made while the server cannot be reached are queued and sent later. */
class FavoriteRecipesQueueTest {

    private val database = newDatabase()
    private val cache = FavoriteRecipeCache(database)
    private val store = PendingFavoriteStore(database)
    private val remote = FakeFavoriteRemote()
    private val scheduler = RecordingScheduler()
    private val repository = FavoriteRecipesRepository(remote, cache, store, scheduler)

    private val offline = ApiException.NetworkError()

    private fun ids(list: List<com.nutriplan.shared.data.model.Recipe>) = list.map { it.id }

    // --- the store ---

    @Test
    fun `the store keeps the latest wish per recipe, oldest wish first`() {
        store.queue(favoriteRecipe("a"), favorite = true)
        store.queue(favoriteRecipe("b"), favorite = true)
        store.queue(favoriteRecipe("a"), favorite = false)

        val waiting = store.waiting()

        assertEquals(listOf("b", "a"), waiting.map { it.recipe.id })
        assertEquals(listOf(true, false), waiting.map { it.favorite })
        assertEquals("Recipe a", waiting.last().recipe.name, "the recipe is kept to show it meanwhile")
    }

    @Test
    fun `the store counts attempts, forgets one wish, or all`() {
        store.queue(favoriteRecipe("a"), favorite = true)
        store.queue(favoriteRecipe("b"), favorite = true)

        store.bumpAttempts("a")
        assertEquals(1, store.waiting().first().attempts)

        store.remove("a")
        assertEquals(listOf("b"), store.waiting().map { it.recipe.id })

        store.clear()
        assertTrue(store.waiting().isEmpty())
    }

    @Test
    fun `an unreadable stored recipe is skipped`() {
        database.pendingFavoriteQueries.upsert("bad", true, "not json", 1L)

        assertTrue(store.waiting().isEmpty())
    }

    // --- toggling while the server cannot be reached ---

    @Test
    fun `offline a save is queued instead of failing, and a sync is requested`() = runTest {
        remote.addFailure = offline

        repository.add(favoriteRecipe("a"))

        assertEquals(listOf("a"), store.waiting().map { it.recipe.id })
        assertTrue(store.waiting().single().favorite)
        assertEquals(1, scheduler.requests)
        assertTrue(cache.getAll().isEmpty(), "the copy only ever holds what the server agreed to")
    }

    @Test
    fun `offline a removal is queued instead of failing`() = runTest {
        remote.removeFailure = offline

        repository.remove(favoriteRecipe("a"))

        assertEquals(false, store.waiting().single().favorite)
    }

    @Test
    fun `a server error is queued too`() = runTest {
        remote.addFailure = ApiException.HttpError(503, null)

        repository.add(favoriteRecipe("a"))

        assertEquals(1, store.waiting().size)
    }

    @Test
    fun `an ended session or a refusal is still an error, not queued`() = runTest {
        remote.addFailure = ApiException.HttpError(401, null)
        assertFailsWith<ApiException.HttpError> { repository.add(favoriteRecipe("a")) }

        remote.addFailure = ApiException.HttpError(404, null)
        assertFailsWith<ApiException.HttpError> { repository.add(favoriteRecipe("b")) }

        assertTrue(store.waiting().isEmpty())
    }

    @Test
    fun `without a queue an offline toggle fails as before`() = runTest {
        val plain = FavoriteRecipesRepository(remote, cache)
        remote.addFailure = offline

        assertFailsWith<ApiException.NetworkError> { plain.add(favoriteRecipe("a")) }
    }

    @Test
    fun `a toggle that reaches the server replaces an older queued wish`() = runTest {
        remote.addFailure = offline
        repository.add(favoriteRecipe("a"))
        remote.addFailure = null
        remote.removeFailure = null

        repository.remove(favoriteRecipe("a"))

        assertTrue(store.waiting().isEmpty())
    }

    // --- showing and sending the queue ---

    @Test
    fun `offline the saved copy is shown with the waiting toggles applied`() = runTest {
        cache.replaceAll(listOf(favoriteRecipe("kept"), favoriteRecipe("gone")))
        remote.listFailure = offline
        remote.addFailure = offline
        remote.removeFailure = offline
        repository.add(favoriteRecipe("new"))
        repository.remove(favoriteRecipe("gone"))

        val result = repository.load()

        assertTrue(result.fromCache)
        assertEquals(listOf("new", "kept"), ids(result.recipes))
    }

    @Test
    fun `loading sends the queue first, so the server's list already has the toggles`() = runTest {
        remote.server = mutableListOf(favoriteRecipe("old"))
        remote.addFailure = offline
        repository.add(favoriteRecipe("new"))
        remote.addFailure = null

        val result = repository.load()

        assertEquals(listOf("new", "old"), ids(result.recipes))
        assertTrue(store.waiting().isEmpty())
        assertEquals(listOf("new", "old"), ids(cache.getAll()))
    }

    @Test
    fun `flush sends the wishes oldest first and updates the copy`() = runTest {
        cache.replaceAll(listOf(favoriteRecipe("x")))
        remote.server = mutableListOf(favoriteRecipe("x"))
        store.queue(favoriteRecipe("a"), favorite = true)
        store.queue(favoriteRecipe("x"), favorite = false)

        val result = repository.flushPending()

        assertEquals(FlushResult(added = 2, failed = 0, waiting = 0), result)
        assertEquals(listOf("a"), remote.added)
        assertEquals(listOf("x"), remote.removed)
        assertEquals(listOf("a"), ids(cache.getAll()))
    }

    @Test
    fun `while still offline the queue is kept, in order`() = runTest {
        store.queue(favoriteRecipe("a"), favorite = true)
        store.queue(favoriteRecipe("b"), favorite = true)
        remote.addFailure = offline

        val result = repository.flushPending()

        assertEquals(FlushResult(added = 0, failed = 0, waiting = 2), result)
        assertEquals(listOf("a"), remote.added, "b was not even tried")
        assertEquals(1, store.waiting().first().attempts)
    }

    @Test
    fun `a wish the server will never accept is dropped without holding back the next`() = runTest {
        remote.server = mutableListOf(favoriteRecipe("x"))
        store.queue(favoriteRecipe("gone"), favorite = true)
        store.queue(favoriteRecipe("x"), favorite = false)
        remote.addFailure = ApiException.HttpError(404, null)

        val result = repository.flushPending()

        assertEquals(FlushResult(added = 1, failed = 1, waiting = 0), result)
        assertTrue(store.waiting().isEmpty())
        assertEquals(listOf("x"), remote.removed)
    }

    @Test
    fun `clearing on sign out forgets the queue too`() = runTest {
        remote.addFailure = offline
        repository.add(favoriteRecipe("a"))

        repository.clearCache()

        assertTrue(store.waiting().isEmpty())
    }

    @Test
    fun `the background job sends both queues and adds up what they did`() = runTest {
        store.queue(favoriteRecipe("a"), favorite = true)
        val meals = MealQueueFlusher { FlushResult(added = 1, failed = 1, waiting = 2) }

        val result = CombinedQueueFlusher(meals, repository).flush()

        assertEquals(FlushResult(added = 2, failed = 1, waiting = 2), result)
    }

    // --- the hearts ---

    @Test
    fun `offline a heart stays as the user set it, with no error`() = runTest {
        val viewModel = FavoriteRecipesViewModel(repository)
        remote.addFailure = offline

        viewModel.toggle(favoriteRecipe("a"))

        assertTrue(viewModel.state.value.isFavorite("a"))
        assertNull(viewModel.state.value.changeError)
        assertTrue(viewModel.state.value.pendingIds.isEmpty())
    }
}
