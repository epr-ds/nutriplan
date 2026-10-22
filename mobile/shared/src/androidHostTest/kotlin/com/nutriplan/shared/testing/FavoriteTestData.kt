package com.nutriplan.shared.testing

import com.nutriplan.shared.data.local.FavoriteRecipeCache
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.model.RecipeIngredient
import com.nutriplan.shared.data.repository.FavoriteRecipesRemote
import kotlinx.coroutines.CompletableDeferred

fun newFavoriteCache(): FavoriteRecipeCache = FavoriteRecipeCache(newDatabase())

/** A fully populated recipe, so a cache round trip proves every field survives. */
fun favoriteRecipe(id: String) = Recipe(
    id = id,
    name = "Recipe $id",
    description = "About $id",
    ingredients = listOf(RecipeIngredient(name = "Water", quantity = 1.5, unit = "cup", calories = 0)),
    instructions = listOf("Boil", "Serve"),
    prepTime = 5,
    cookTime = 10,
    servings = 2,
    imageUrl = "https://images.example/$id.jpg",
    nutritionalInfo = NutritionalInfo(calories = 100, protein = 5.5, carbs = 10.0, fat = 2.0, sugar = 1.0),
    dietaryTypes = listOf("vegan", "keto"),
)

/** A scriptable [FavoriteRecipesRemote]: a server-side list, failures, and a gate to hold a call open. */
class FakeFavoriteRemote(initial: List<Recipe> = emptyList()) : FavoriteRecipesRemote {
    /** What the server holds, most recently saved first. */
    var server: MutableList<Recipe> = initial.toMutableList()
    var listFailure: Throwable? = null
    var addFailure: Throwable? = null
    var removeFailure: Throwable? = null
    var gate: CompletableDeferred<Unit>? = null

    val pagesRequested = mutableListOf<Int>()
    val added = mutableListOf<String>()
    val removed = mutableListOf<String>()

    override suspend fun list(page: Int, limit: Int): List<Recipe> {
        pagesRequested += page
        listFailure?.let { throw it }
        return server.drop((page - 1) * limit).take(limit)
    }

    override suspend fun add(recipeId: String) {
        added += recipeId
        gate?.await()
        addFailure?.let { throw it }
        // Like the service: saving is idempotent and puts the recipe first.
        if (server.none { it.id == recipeId }) server.add(0, favoriteRecipe(recipeId))
    }

    override suspend fun remove(recipeId: String) {
        removed += recipeId
        gate?.await()
        removeFailure?.let { throw it }
        server.removeAll { it.id == recipeId }
    }
}
