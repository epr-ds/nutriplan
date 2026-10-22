package com.nutriplan.shared.testing

import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.local.MealPlanCache
import com.nutriplan.shared.data.local.PendingMealStore
import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.MealPlanQuery
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.data.model.NutritionDisclaimer
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.model.RecipeSearchQuery
import com.nutriplan.shared.data.model.UpdateMealRequest
import com.nutriplan.shared.data.repository.DietaryRepository
import com.nutriplan.shared.data.repository.PendingMealSync
import com.nutriplan.shared.data.repository.SyncScheduler
import kotlinx.coroutines.CompletableDeferred

/** A database with the plan cache and the queue on it, the way the app wires them. */
class QueueFixture(val database: NutriPlanDatabase = newDatabase()) {
    val cache = MealPlanCache(database)
    val store = PendingMealStore(database)
    val remote = FakePlanRemote()
    val scheduler = RecordingScheduler()
    val sync = PendingMealSync(remote, store, cache, scheduler)
}

/** A [SyncScheduler] that only counts how often a background sync was asked for. */
class RecordingScheduler : SyncScheduler {
    var requests = 0

    override fun requestSync() {
        requests++
    }
}

/** A recipe with nutrition, for a meal that is added while offline. */
fun queuedRecipe(id: String = "r1") = Recipe(
    id = id,
    name = "Recipe $id",
    imageUrl = "https://images.example/$id.jpg",
    nutritionalInfo = NutritionalInfo(calories = 300, protein = 20.0, carbs = 30.0, fat = 10.0, sugar = 5.0),
)

fun addRequest(recipeId: String = "r1", mealType: String = "lunch", servings: Double = 2.0) =
    AddMealRequest(mealType = mealType, recipeId = recipeId, servings = servings)

/** A scriptable plan API: what it holds, what it was asked, and failures to throw. */
class FakePlanRemote : DietaryRepository {
    var plan: MealPlan? = fullPlan("p1")
    var planFailure: Throwable? = null

    /** Thrown by the next add-meal calls; a list is consumed one call at a time, then calls succeed. */
    var addFailures: MutableList<Throwable?> = mutableListOf()
    var updateFailure: Throwable? = null
    var gate: CompletableDeferred<Unit>? = null

    /** Every add-meal call, including the ones that failed. */
    val added = mutableListOf<Pair<String, AddMealRequest>>()

    /** The meals the server really has, from the add-meal calls that succeeded. */
    private val created = mutableListOf<Pair<String, AddMealRequest>>()
    val updated = mutableListOf<Triple<String, String, UpdateMealRequest>>()
    private var counter = 0

    override suspend fun getMealPlan(planId: String): MealPlan {
        planFailure?.let { throw it }
        // The server's plan holds every meal it has been given.
        return plan!!.copy(meals = plan!!.meals + created.filter { it.first == planId }.mapIndexed { i, (_, r) ->
            PlanMeal(id = "srv-$i", mealType = r.mealType, servings = r.servings)
        })
    }

    override suspend fun addMeal(planId: String, request: AddMealRequest): PlanMeal {
        added += planId to request
        gate?.await()
        addFailures.removeFirstOrNull()?.let { throw it }
        created += planId to request
        counter++
        return PlanMeal(id = "srv-meal-$counter", mealType = request.mealType, servings = request.servings)
    }

    override suspend fun updateMeal(planId: String, mealId: String, request: UpdateMealRequest): PlanMeal {
        updated += Triple(planId, mealId, request)
        updateFailure?.let { throw it }
        return PlanMeal(id = mealId, mealType = "lunch", servings = 1.0, dayIndex = request.dayIndex)
    }

    override suspend fun getRecipe(recipeId: String): Recipe = queuedRecipe(recipeId)

    override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan = error("unused")
    override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlanSummary> = error("unused")
    override suspend fun updateMealPlanStatus(planId: String, status: String): MealPlan = error("unused")
    override suspend fun removeMeal(planId: String, mealId: String): Unit = error("unused")
    override suspend fun searchRecipes(query: RecipeSearchQuery): List<Recipe> = error("unused")
    override suspend fun getNutritionDisclaimer(): NutritionDisclaimer = error("unused")
}
