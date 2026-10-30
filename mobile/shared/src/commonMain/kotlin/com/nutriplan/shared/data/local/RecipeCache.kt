package com.nutriplan.shared.data.local

import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.model.Recipe
import kotlinx.serialization.json.Json

/**
 * On-device copy of the recipe catalog that was searched or opened (DPL-403), so the recipes a user
 * browsed can be read while the device is offline. It holds exactly what the server last sent, in
 * the order the catalog served them.
 */
class RecipeCache(private val database: NutriPlanDatabase) {

    private val queries = database.recipeQueries

    /** Tolerant on read: a cached blob written by an older app version must never crash the app. */
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /** Every cached recipe, most recent first. A row that cannot be read is skipped. */
    fun getAll(): List<Recipe> =
        queries.selectAll().executeAsList().mapNotNull { text ->
            runCatching { json.decodeFromString(Recipe.serializer(), text) }.getOrNull()
        }

    /** One cached recipe, or null when it was never cached. */
    fun get(recipeId: String): Recipe? = queries.selectById(recipeId).executeAsOneOrNull()?.let { text ->
        runCatching { json.decodeFromString(Recipe.serializer(), text) }.getOrNull()
    }

    /** Replace the cached copy with [recipes], in that order. */
    fun saveAll(recipes: List<Recipe>) {
        database.transaction {
            queries.deleteAll()
            recipes.forEachIndexed { position, recipe ->
                queries.insertRecipe(
                    recipe_id = recipe.id,
                    position = position.toLong(),
                    recipe = json.encodeToString(Recipe.serializer(), recipe),
                )
            }
        }
    }

    /** Forget every cached recipe (for example on logout). */
    fun clear() {
        queries.deleteAll()
    }
}