package com.nutriplan.shared.data.local

import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.model.Recipe
import kotlinx.serialization.json.Json

/** A favorite toggle waiting to be sent: save [recipe] when [favorite], remove it otherwise. */
data class PendingFavorite(
    val recipe: Recipe,
    val favorite: Boolean,
    val attempts: Int,
)

/**
 * On-device queue of favorite toggles made while the server could not be reached (DPL-407). It
 * keeps one wish per recipe, the latest one, in the order the wishes were made.
 */
class PendingFavoriteStore(private val database: NutriPlanDatabase) {

    private val queries = database.pendingFavoriteQueries

    /** Tolerant on read: a stored blob written by an older app version must never crash the app. */
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /** Remember that [recipe] should be saved ([favorite]) or removed; replaces an earlier wish. */
    fun queue(recipe: Recipe, favorite: Boolean) {
        database.transaction {
            val next = (queries.selectNextOrder().executeAsOneOrNull() ?: 0L) + 1L
            queries.upsert(recipe.id, favorite, json.encodeToString(Recipe.serializer(), recipe), next)
        }
    }

    /** Every waiting wish, oldest first. A row that cannot be read is skipped. */
    fun waiting(): List<PendingFavorite> =
        queries.selectAll().executeAsList().mapNotNull { row ->
            val decoded = runCatching { json.decodeFromString(Recipe.serializer(), row.recipe) }.getOrNull()
            decoded?.let { PendingFavorite(it.copy(id = row.recipe_id), row.favorite, row.attempts.toInt()) }
        }

    /** Count one more try that did not get through. */
    fun bumpAttempts(recipeId: String) = queries.bumpAttempts(recipeId)

    /** Forget the wish for [recipeId] (sent, or given up). */
    fun remove(recipeId: String) = queries.deleteByRecipe(recipeId)

    /** Forget every wish (for example on logout). */
    fun clear() = queries.deleteAll()
}
