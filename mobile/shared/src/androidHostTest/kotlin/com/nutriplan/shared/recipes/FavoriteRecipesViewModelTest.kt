package com.nutriplan.shared.recipes

import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.repository.FavoriteRecipesRepository
import com.nutriplan.shared.testing.FakeFavoriteRemote
import com.nutriplan.shared.testing.favoriteRecipe
import com.nutriplan.shared.testing.newFavoriteCache
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class FavoriteRecipesViewModelTest {

    private val remote = FakeFavoriteRemote()
    private val cache = newFavoriteCache()
    private val viewModel = FavoriteRecipesViewModel(FavoriteRecipesRepository(remote, cache))

    private fun ids() = viewModel.state.value.recipes.map { it.id }

    // --- loading ---

    @Test
    fun `starts empty and not loaded`() {
        val state = viewModel.state.value

        assertTrue(state.recipes.isEmpty())
        assertFalse(state.hasLoaded)
        assertFalse(state.isLoading)
    }

    @Test
    fun `load shows the server's favorites`() = runTest {
        remote.server = mutableListOf(favoriteRecipe("a"), favoriteRecipe("b"))

        viewModel.load()

        val state = viewModel.state.value
        assertEquals(listOf("a", "b"), ids())
        assertTrue(state.hasLoaded)
        assertFalse(state.isLoading)
        assertFalse(state.isOffline)
        assertNull(state.loadError)
        assertEquals(setOf("a", "b"), state.ids)
        assertTrue(state.isFavorite("a"))
        assertFalse(state.isFavorite("zzz"))
    }

    @Test
    fun `offline load shows the saved copy and says so`() = runTest {
        cache.replaceAll(listOf(favoriteRecipe("saved")))
        remote.listFailure = ApiException.NetworkError()

        viewModel.load()

        assertEquals(listOf("saved"), ids())
        assertTrue(viewModel.state.value.isOffline)
        assertTrue(viewModel.state.value.hasLoaded)
    }

    @Test
    fun `a failed load keeps what was shown and reports why`() = runTest {
        remote.server = mutableListOf(favoriteRecipe("a"))
        viewModel.load()
        remote.listFailure = ApiException.HttpError(401, null)

        viewModel.load()

        assertEquals(listOf("a"), ids())
        assertEquals(FavoriteError.SESSION_EXPIRED, viewModel.state.value.loadError)
        assertFalse(viewModel.state.value.isLoading)
    }

    @Test
    fun `load failures map to stable codes`() = runTest {
        suspend fun errorFor(failure: Throwable): FavoriteError? {
            val fake = FakeFavoriteRemote().apply { listFailure = failure }
            val vm = FavoriteRecipesViewModel(FavoriteRecipesRepository(fake, newFavoriteCache()))
            vm.load()
            return vm.state.value.loadError
        }

        assertEquals(FavoriteError.SESSION_EXPIRED, errorFor(ApiException.HttpError(401, null)))
        assertEquals(FavoriteError.UNKNOWN, errorFor(ApiException.HttpError(418, null)))
    }

    @Test
    fun `a retry clears the error`() = runTest {
        remote.listFailure = ApiException.HttpError(401, null)
        viewModel.load()
        remote.listFailure = null
        remote.server = mutableListOf(favoriteRecipe("a"))

        viewModel.load()

        assertNull(viewModel.state.value.loadError)
        assertEquals(listOf("a"), ids())
    }

    // --- toggling ---

    @Test
    fun `toggling a recipe saves it at the front`() = runTest {
        remote.server = mutableListOf(favoriteRecipe("a"))
        viewModel.load()

        viewModel.toggle(favoriteRecipe("new"))

        assertEquals(listOf("new", "a"), ids())
        assertEquals(listOf("new"), remote.added)
        assertTrue(viewModel.state.value.pendingIds.isEmpty())
        assertEquals(listOf("new", "a"), cache.getAll().map { it.id })
    }

    @Test
    fun `toggling a favorite removes it`() = runTest {
        remote.server = mutableListOf(favoriteRecipe("a"), favoriteRecipe("b"))
        viewModel.load()

        viewModel.toggle(favoriteRecipe("a"))

        assertEquals(listOf("b"), ids())
        assertEquals(listOf("a"), remote.removed)
        assertEquals(listOf("b"), cache.getAll().map { it.id })
    }

    @Test
    fun `the heart flips immediately, before the server answers`() = runTest {
        val gate = CompletableDeferred<Unit>()
        remote.gate = gate

        val job = launch { viewModel.toggle(favoriteRecipe("new")) }
        testScheduler.advanceUntilIdle()

        assertTrue(viewModel.state.value.isFavorite("new"))
        assertEquals(setOf("new"), viewModel.state.value.pendingIds)

        gate.complete(Unit)
        job.join()
        assertTrue(viewModel.state.value.isFavorite("new"))
        assertTrue(viewModel.state.value.pendingIds.isEmpty())
    }

    @Test
    fun `a failed save puts the heart back and says why`() = runTest {
        remote.addFailure = ApiException.NetworkError()

        viewModel.toggle(favoriteRecipe("new"))

        val state = viewModel.state.value
        assertFalse(state.isFavorite("new"))
        assertEquals(FavoriteError.NETWORK, state.changeError)
        assertTrue(state.pendingIds.isEmpty())
        assertTrue(cache.getAll().isEmpty())
    }

    @Test
    fun `a failed removal puts the recipe back where it was`() = runTest {
        remote.server = mutableListOf(favoriteRecipe("a"), favoriteRecipe("b"), favoriteRecipe("c"))
        viewModel.load()
        remote.removeFailure = ApiException.HttpError(500, null)

        viewModel.toggle(favoriteRecipe("b"))

        assertEquals(listOf("a", "b", "c"), ids())
        assertEquals(FavoriteError.SERVER_PROBLEM, viewModel.state.value.changeError)
    }

    @Test
    fun `taps on a recipe whose change is still in flight are ignored`() = runTest {
        val gate = CompletableDeferred<Unit>()
        remote.gate = gate

        val first = launch { viewModel.toggle(favoriteRecipe("new")) }
        testScheduler.advanceUntilIdle()
        viewModel.toggle(favoriteRecipe("new"))
        gate.complete(Unit)
        first.join()

        assertEquals(listOf("new"), remote.added)
        assertTrue(remote.removed.isEmpty())
        assertTrue(viewModel.state.value.isFavorite("new"))
    }

    @Test
    fun `different recipes can change at the same time`() = runTest {
        val gate = CompletableDeferred<Unit>()
        remote.gate = gate

        val one = launch { viewModel.toggle(favoriteRecipe("one")) }
        val two = launch { viewModel.toggle(favoriteRecipe("two")) }
        testScheduler.advanceUntilIdle()
        assertEquals(setOf("one", "two"), viewModel.state.value.pendingIds)

        gate.complete(Unit)
        one.join()
        two.join()

        assertEquals(setOf("one", "two"), viewModel.state.value.ids)
    }

    @Test
    fun `toggling twice ends where it started`() = runTest {
        remote.server = mutableListOf(favoriteRecipe("a"))
        viewModel.load()

        viewModel.toggle(favoriteRecipe("a"))
        viewModel.toggle(favoriteRecipe("a"))

        assertEquals(listOf("a"), ids())
    }

    @Test
    fun `cancelling a change puts the heart back and rethrows`() = runTest {
        remote.gate = CompletableDeferred()

        val job = launch { viewModel.toggle(favoriteRecipe("new")) }
        testScheduler.advanceUntilIdle()
        assertTrue(viewModel.state.value.isFavorite("new"))
        job.cancel()
        job.join()

        assertFalse(viewModel.state.value.isFavorite("new"))
        assertTrue(viewModel.state.value.pendingIds.isEmpty())
        assertNull(viewModel.state.value.changeError)
    }

    @Test
    fun `the message about an undone change can be dismissed`() = runTest {
        remote.addFailure = ApiException.NetworkError()
        viewModel.toggle(favoriteRecipe("new"))

        viewModel.clearChangeError()

        assertNull(viewModel.state.value.changeError)
    }

    @Test
    fun `a new change clears the previous message`() = runTest {
        remote.addFailure = ApiException.NetworkError()
        viewModel.toggle(favoriteRecipe("new"))
        remote.addFailure = null

        viewModel.toggle(favoriteRecipe("other"))

        assertNull(viewModel.state.value.changeError)
    }

    // --- sign out ---

    @Test
    fun `reset forgets everything in memory and on the device`() = runTest {
        remote.server = mutableListOf(favoriteRecipe("a"))
        viewModel.load()

        viewModel.reset()

        assertEquals(FavoriteRecipesUiState(), viewModel.state.value)
        assertTrue(cache.getAll().isEmpty())
    }
}
