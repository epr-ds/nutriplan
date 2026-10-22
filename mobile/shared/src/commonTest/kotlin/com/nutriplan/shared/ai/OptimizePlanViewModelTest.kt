package com.nutriplan.shared.ai

import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.AiRecommendationRequest
import com.nutriplan.shared.data.model.AiRecommendations
import com.nutriplan.shared.data.model.AnalyzeMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.MealAnalysis
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.MealPlanQuery
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.data.model.NutritionDisclaimer
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.NutritionalSummary
import com.nutriplan.shared.data.model.OptimizePlanRequest
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.PlanMealRecipe
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.model.RecipeSearchQuery
import com.nutriplan.shared.data.model.UpdateMealRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.repository.AiRepository
import com.nutriplan.shared.data.repository.DietaryRepository
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class OptimizePlanViewModelTest {

    private class FakeAi : AiRepository {
        var failure: Throwable? = null
        val gates = ArrayDeque<CompletableDeferred<Unit>>()
        val replies = ArrayDeque<MealPlan>()
        val requests = mutableListOf<OptimizePlanRequest>()

        override suspend fun optimizePlan(request: OptimizePlanRequest): MealPlan {
            requests += request
            val reply = replies.removeFirstOrNull() ?: optimized
            gates.removeFirstOrNull()?.await()
            failure?.let { throw it }
            return reply
        }

        override suspend fun recommendations(request: AiRecommendationRequest): AiRecommendations = error("unused")

        override suspend fun analyzeMeal(request: AnalyzeMealRequest): MealAnalysis = error("unused")
    }

    private class FakeDietary : DietaryRepository {
        var plan = original
        var planFailure: Throwable? = null
        /** Fails the update of this meal (once, while set). */
        var failMealId: String? = null
        val updates = mutableListOf<Pair<String, UpdateMealRequest>>()

        override suspend fun getMealPlan(planId: String): MealPlan {
            planFailure?.let { throw it }
            return plan
        }

        override suspend fun updateMeal(planId: String, mealId: String, request: UpdateMealRequest): PlanMeal {
            if (mealId == failMealId) throw ApiException.NetworkError()
            updates += mealId to request
            return PlanMeal(id = mealId, mealType = "lunch", servings = request.servings ?: 1.0)
        }

        override suspend fun getRecipe(recipeId: String): Recipe = error("unused")
        override suspend fun addMeal(planId: String, request: AddMealRequest): PlanMeal = error("unused")
        override suspend fun removeMeal(planId: String, mealId: String): Unit = error("unused")
        override suspend fun searchRecipes(query: RecipeSearchQuery): List<Recipe> = error("unused")
        override suspend fun getNutritionDisclaimer(): NutritionDisclaimer = error("unused")
        override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlanSummary> = error("unused")
        override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan = error("unused")
        override suspend fun updateMealPlanStatus(planId: String, status: String): MealPlan = error("unused")
    }

    private val ai = FakeAi()
    private val dietary = FakeDietary()
    private val viewModel = OptimizePlanViewModel(AiAdvisor(ai), dietary)

    @Test
    fun `start loads the plan to compare against`() = runTest {
        viewModel.start("p1")

        val state = viewModel.state.value
        assertEquals(original, state.original)
        assertFalse(state.isLoadingPlan)
        assertEquals(AiAdvisor.GOALS.first(), state.goal)
        assertTrue(ai.requests.isEmpty())
    }

    @Test
    fun `a plan that cannot be loaded is reported and can be retried`() = runTest {
        dietary.planFailure = ApiException.HttpError(404, null)
        viewModel.start("p1")
        assertEquals(AiError.NOT_FOUND, viewModel.state.value.loadError)

        dietary.planFailure = null
        viewModel.start("p1")

        assertNull(viewModel.state.value.loadError)
        assertEquals(original, viewModel.state.value.original)
    }

    @Test
    fun `optimizing asks for the chosen goal and lists the serving changes`() = runTest {
        viewModel.start("p1")
        viewModel.onGoalChange("increase_protein")

        viewModel.optimize()

        assertEquals(OptimizePlanRequest(planId = "p1", goal = "increase_protein"), ai.requests.single())
        val state = viewModel.state.value
        assertEquals(optimized, state.draft)
        assertEquals(
            listOf(
                MealServingChange("m1", "breakfast", "Oats", "2026-10-01", before = 1.0, after = 1.5),
                MealServingChange("m3", "dinner", null, null, before = 2.0, after = 1.0),
            ),
            state.changes,
        )
        assertFalse(state.isUnchanged)
        assertEquals(1900, state.dailyAverageBefore?.calories)
        assertEquals(1750, state.dailyAverageAfter?.calories)
    }

    @Test
    fun `a draft with nothing different says the plan is already right`() = runTest {
        ai.replies += original.copy(status = "draft")
        viewModel.start("p1")

        viewModel.optimize()

        assertTrue(viewModel.state.value.isUnchanged)
    }

    @Test
    fun `nothing is asked before the plan is loaded`() = runTest {
        dietary.planFailure = ApiException.NetworkError()
        viewModel.start("p1")

        viewModel.optimize()

        assertTrue(ai.requests.isEmpty())
    }

    @Test
    fun `an optimization failure is a typed error and can be retried`() = runTest {
        viewModel.start("p1")
        ai.failure = ApiException.HttpError(503, null)
        viewModel.optimize()
        assertEquals(AiError.SERVER_PROBLEM, viewModel.state.value.optimizeError)
        assertNull(viewModel.state.value.draft)

        ai.failure = null
        viewModel.optimize()

        assertNull(viewModel.state.value.optimizeError)
        assertEquals(optimized, viewModel.state.value.draft)
    }

    @Test
    fun `changing the goal drops the draft made for the old one`() = runTest {
        viewModel.start("p1")
        viewModel.optimize()

        viewModel.onGoalChange("reduce_calories")

        assertNull(viewModel.state.value.draft)
        assertTrue(viewModel.state.value.changes.isEmpty())
        assertEquals("reduce_calories", viewModel.state.value.goal)
    }

    @Test
    fun `an unknown goal is ignored`() = runTest {
        viewModel.onGoalChange("gain_weight")

        assertEquals(AiAdvisor.GOALS.first(), viewModel.state.value.goal)
    }

    @Test
    fun `an answer for a goal no longer chosen is dropped`() = runTest {
        viewModel.start("p1")
        val slow = CompletableDeferred<Unit>()
        ai.gates += slow

        val job = launch { viewModel.optimize() }
        runCurrent()
        assertTrue(viewModel.state.value.isOptimizing)
        viewModel.onGoalChange("reduce_calories")
        slow.complete(Unit)
        job.join()

        assertNull(viewModel.state.value.draft)
        assertFalse(viewModel.state.value.isOptimizing)
    }

    @Test
    fun `accepting saves the new servings of every changed meal`() = runTest {
        viewModel.start("p1")
        viewModel.optimize()

        viewModel.accept()

        assertEquals(
            listOf("m1" to UpdateMealRequest(servings = 1.5), "m3" to UpdateMealRequest(servings = 1.0)),
            dietary.updates,
        )
        assertTrue(viewModel.state.value.isAccepted)
        assertFalse(viewModel.state.value.isAccepting)
    }

    @Test
    fun `a failed accept keeps what was saved and the retry saves only the rest`() = runTest {
        viewModel.start("p1")
        viewModel.optimize()
        dietary.failMealId = "m3"

        viewModel.accept()

        assertEquals(AiError.NETWORK, viewModel.state.value.acceptError)
        assertEquals(setOf("m1"), viewModel.state.value.appliedMealIds)
        assertFalse(viewModel.state.value.isAccepted)

        dietary.failMealId = null
        viewModel.accept()

        assertEquals(listOf("m1", "m3"), dietary.updates.map { it.first })
        assertTrue(viewModel.state.value.isAccepted)
        assertNull(viewModel.state.value.acceptError)
    }

    @Test
    fun `nothing to accept without changes`() = runTest {
        ai.replies += original.copy(status = "draft")
        viewModel.start("p1")
        viewModel.optimize()

        viewModel.accept()

        assertTrue(dietary.updates.isEmpty())
        assertFalse(viewModel.state.value.isAccepted)
    }

    @Test
    fun `once accepted the goal and the draft are fixed`() = runTest {
        viewModel.start("p1")
        viewModel.optimize()
        viewModel.accept()

        viewModel.onGoalChange("reduce_calories")
        viewModel.optimize()

        assertEquals(AiAdvisor.GOALS.first(), viewModel.state.value.goal)
        assertEquals(1, ai.requests.size)
    }

    private companion object {
        val original = MealPlan(
            id = "p1",
            name = "Week",
            startDate = "2026-10-01",
            endDate = "2026-10-07",
            dailyCalorieTarget = 1800,
            status = "active",
            meals = listOf(
                PlanMeal(
                    id = "m1",
                    mealType = "breakfast",
                    servings = 1.0,
                    dayIndex = 0,
                    recipe = PlanMealRecipe(id = "r1", name = "Oats"),
                ),
                PlanMeal(id = "m2", mealType = "lunch", servings = 1.0, dayIndex = 1),
                PlanMeal(id = "m3", mealType = "dinner", servings = 2.0),
            ),
            nutritionalSummary = NutritionalSummary(dailyAverage = NutritionalInfo(calories = 1900, protein = 80.0)),
        )

        val optimized = original.copy(
            status = "draft",
            meals = listOf(
                PlanMeal(id = "m1", mealType = "breakfast", servings = 1.5, dayIndex = 0),
                PlanMeal(id = "m2", mealType = "lunch", servings = 1.0, dayIndex = 1),
                PlanMeal(id = "m3", mealType = "dinner", servings = 1.0),
            ),
            nutritionalSummary = NutritionalSummary(dailyAverage = NutritionalInfo(calories = 1750, protein = 95.0)),
        )
    }
}
