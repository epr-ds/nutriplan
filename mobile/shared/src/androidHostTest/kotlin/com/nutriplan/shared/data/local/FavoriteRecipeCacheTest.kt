package com.nutriplan.shared.data.local

import com.nutriplan.shared.testing.favoriteRecipe
import com.nutriplan.shared.testing.newDatabase
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class FavoriteRecipeCacheTest {

    private val database = newDatabase()
    private val cache = FavoriteRecipeCache(database)

    @Test
    fun `an empty cache has no favorites`() {
        assertTrue(cache.getAll().isEmpty())
    }

    @Test
    fun `recipes round trip with every field, in the order they were given`() {
        val recipes = listOf(favoriteRecipe("b"), favoriteRecipe("a"), favoriteRecipe("c"))

        cache.replaceAll(recipes)

        assertEquals(recipes, cache.getAll())
    }

    @Test
    fun `replacing drops what is no longer there`() {
        cache.replaceAll(listOf(favoriteRecipe("a"), favoriteRecipe("b")))

        cache.replaceAll(listOf(favoriteRecipe("c")))

        assertEquals(listOf("c"), cache.getAll().map { it.id })
    }

    @Test
    fun `a newly saved recipe goes in front`() {
        cache.replaceAll(listOf(favoriteRecipe("a"), favoriteRecipe("b")))

        cache.addFirst(favoriteRecipe("new"))

        assertEquals(listOf("new", "a", "b"), cache.getAll().map { it.id })
    }

    @Test
    fun `adding to an empty cache works`() {
        cache.addFirst(favoriteRecipe("only"))

        assertEquals(listOf("only"), cache.getAll().map { it.id })
    }

    @Test
    fun `saving again moves a recipe to the front instead of duplicating it`() {
        cache.replaceAll(listOf(favoriteRecipe("a"), favoriteRecipe("b"), favoriteRecipe("c")))

        cache.addFirst(favoriteRecipe("c"))

        assertEquals(listOf("c", "a", "b"), cache.getAll().map { it.id })
    }

    @Test
    fun `several additions keep the newest first`() {
        cache.addFirst(favoriteRecipe("1"))
        cache.addFirst(favoriteRecipe("2"))
        cache.addFirst(favoriteRecipe("3"))

        assertEquals(listOf("3", "2", "1"), cache.getAll().map { it.id })
    }

    @Test
    fun `removing forgets one favorite and ignores an unknown one`() {
        cache.replaceAll(listOf(favoriteRecipe("a"), favoriteRecipe("b")))

        cache.remove("a")
        cache.remove("never-saved")

        assertEquals(listOf("b"), cache.getAll().map { it.id })
    }

    @Test
    fun `clear forgets everything`() {
        cache.replaceAll(listOf(favoriteRecipe("a"), favoriteRecipe("b")))

        cache.clear()

        assertTrue(cache.getAll().isEmpty())
    }

    @Test
    fun `a row that cannot be read is skipped instead of failing the list`() {
        cache.replaceAll(listOf(favoriteRecipe("a")))
        database.favoriteRecipeQueries.insertRecipe(recipe_id = "bad", position = 5L, recipe = "not json")

        assertEquals(listOf("a"), cache.getAll().map { it.id })
    }

    @Test
    fun `a row written by a newer app with extra fields still reads`() {
        database.favoriteRecipeQueries.insertRecipe(
            recipe_id = "x",
            position = 0L,
            recipe = """{"id":"x","name":"Future","someNewField":42}""",
        )

        assertEquals("Future", cache.getAll().single().name)
    }
}
