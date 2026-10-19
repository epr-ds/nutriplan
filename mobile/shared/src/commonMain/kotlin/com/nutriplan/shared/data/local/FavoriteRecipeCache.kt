package com.nutriplan.shared.data.local

import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.model.Recipe
import kotlinx.serialization.json.Json

/**
 * On-device copy of the user's favorite recipes (DPL-607), so the favorites list can be shown when
 * the server cannot be reached. It holds exactly what the server last sent, in the server's order
 * (most recently saved first).
 */
class FavoriteRecipeCache(private val database: NutriPlanDatabase) {

    private val queries = database.favoriteRecipeQueries

    /** Tolerant on read: a cached blob written by an older app version must never crash the app. */
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /** Every cached favorite, most recently saved first. A row that cannot be read is skipped. */
    fun getAll(): List<Recipe> =
        queries.selectAll().executeAsList().mapNotNull { text ->
            runCatching { json.decodeFromString(Recipe.serializer(), text) }.getOrNull()
        }

    /** Replace everything with [recipes] (in that order) atomically. */
    fun replaceAll(recipes: List<Recipe>) {
        database.transaction {
            queries.deleteAll()
            recipes.forEachIndexed { position, recipe -> insert(recipe, position.toLong()) }
        }
    }

    /** Save [recipe] in front of the others (or move it there if it is already cached). */
    fun addFirst(recipe: Recipe) {
        database.transaction {
            val first = queries.selectFirstPosition().executeAsOneOrNull()
            insert(recipe, (first ?: 0L) - 1L)
        }
    }

    /** Forget one favorite. */
    fun remove(recipeId: String) {
        queries.deleteRecipe(recipeId)
    }

    /** Forget every favorite (for example on logout). */
    fun clear() {
        queries.deleteAll()
    }

    private fun insert(recipe: Recipe, position: Long) {
        queries.insertRecipe(
            recipe_id = recipe.id,
            position = position,
            recipe = json.encodeToString(Recipe.serializer(), recipe),
        )
    }
}
