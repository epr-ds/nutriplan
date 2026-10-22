package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.testing.FakeFavoriteRemote
import com.nutriplan.shared.testing.favoriteRecipe
import com.nutriplan.shared.testing.newFavoriteCache
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class FavoriteRecipesRepositoryTest {

    private val remote = FakeFavoriteRemote()
    private val cache = newFavoriteCache()
    private val repository = FavoriteRecipesRepository(remote, cache)

    private fun recipes(count: Int, prefix: String = "r") = List(count) { favoriteRecipe("$prefix$it") }

    @Test
    fun `load returns the server's favorites and saves them on the device`() = runTest {
        remote.server = recipes(3).toMutableList()

        val result = repository.load()

        assertEquals(recipes(3), result.recipes)
        assertFalse(result.fromCache)
        assertEquals(recipes(3), cache.getAll())
    }

    @Test
    fun `load reads every page`() = runTest {
        remote.server = recipes(150).toMutableList()

        val result = repository.load()

        assertEquals(150, result.recipes.size)
        assertEquals(listOf(1, 2), remote.pagesRequested)
        assertEquals(150, cache.getAll().size)
    }

    @Test
    fun `a full last page asks for one more and stops at the empty page`() = runTest {
        remote.server = recipes(100).toMutableList()

        val result = repository.load()

        assertEquals(100, result.recipes.size)
        assertEquals(listOf(1, 2), remote.pagesRequested)
    }

    @Test
    fun `a recipe repeated across pages is listed once`() = runTest {
        // Saved while paging: the same recipe shows up at the end of page 1 and the start of page 2.
        val all = recipes(100) + favoriteRecipe("r99") + recipes(1, prefix = "z")
        remote.server = all.toMutableList()

        val result = repository.load()

        assertEquals(101, result.recipes.size)
        assertEquals(result.recipes.map { it.id }.distinct(), result.recipes.map { it.id })
    }

    @Test
    fun `load replaces what the device had with what the server has now`() = runTest {
        cache.replaceAll(listOf(favoriteRecipe("gone"), favoriteRecipe("kept")))
        remote.server = mutableListOf(favoriteRecipe("kept"), favoriteRecipe("new"))

        repository.load()

        assertEquals(listOf("kept", "new"), cache.getAll().map { it.id })
    }

    @Test
    fun `an offline device is shown the saved copy`() = runTest {
        cache.replaceAll(recipes(2))
        remote.listFailure = ApiException.NetworkError()

        val result = repository.load()

        assertEquals(recipes(2), result.recipes)
        assertTrue(result.fromCache)
    }

    @Test
    fun `a server error is answered from the saved copy too`() = runTest {
        cache.replaceAll(recipes(2))
        remote.listFailure = ApiException.HttpError(503, null)

        assertTrue(repository.load().fromCache)
    }

    @Test
    fun `offline with nothing saved gives an empty saved list`() = runTest {
        remote.listFailure = ApiException.NetworkError()

        val result = repository.load()

        assertTrue(result.recipes.isEmpty())
        assertTrue(result.fromCache)
    }

    @Test
    fun `a rejected session is never answered from the saved copy`() = runTest {
        cache.replaceAll(recipes(2))
        remote.listFailure = ApiException.HttpError(401, null)

        assertFailsWith<ApiException.HttpError> { repository.load() }
        assertEquals(2, cache.getAll().size, "the copy is kept")
    }

    @Test
    fun `add saves on the server first and then puts the recipe in front on the device`() = runTest {
        cache.replaceAll(recipes(2))

        repository.add(favoriteRecipe("new"))

        assertEquals(listOf("new"), remote.added)
        assertEquals(listOf("new", "r0", "r1"), cache.getAll().map { it.id })
    }

    @Test
    fun `a failed add leaves the saved copy untouched`() = runTest {
        cache.replaceAll(recipes(2))
        remote.addFailure = ApiException.NetworkError()

        assertFailsWith<ApiException.NetworkError> { repository.add(favoriteRecipe("new")) }

        assertEquals(listOf("r0", "r1"), cache.getAll().map { it.id })
    }

    @Test
    fun `remove deletes on the server and then on the device`() = runTest {
        cache.replaceAll(recipes(2))

        repository.remove(favoriteRecipe("r0"))

        assertEquals(listOf("r0"), remote.removed)
        assertEquals(listOf("r1"), cache.getAll().map { it.id })
    }

    @Test
    fun `a failed remove leaves the saved copy untouched`() = runTest {
        cache.replaceAll(recipes(2))
        remote.removeFailure = ApiException.HttpError(500, null)

        assertFailsWith<ApiException.HttpError> { repository.remove(favoriteRecipe("r0")) }

        assertEquals(2, cache.getAll().size)
    }

    @Test
    fun `clearing the cache forgets the saved copy`() {
        cache.replaceAll(recipes(2))

        repository.clearCache()

        assertTrue(cache.getAll().isEmpty())
    }
}
