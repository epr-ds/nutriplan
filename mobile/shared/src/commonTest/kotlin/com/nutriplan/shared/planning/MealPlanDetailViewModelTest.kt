package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.MealPlanQuery
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.model.RecipeQuery
import com.nutriplan.shared.data.model.UpdateMealPlanRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.repository.DietaryRepository
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class MealPlanDetailViewModelTest {

    private class FakeDietary : DietaryRepository {
        var plan: MealPlan? = null
        var failure: Throwable? = null
        var gate: CompletableDeferred<Unit>? = null
        var requested: String? = null

        override suspend fun getMealPlan(planId: String): MealPlan {
            requested = planId
            gate?.await()
            failure?.let { throw it }
            return plan ?: throw ApiException.HttpError(404, null)
        }

        override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlan> = error("unused")
        override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan = error("unused")
        override suspend fun updateMealPlan(planId: String, request: UpdateMealPlanRequest): MealPlan = error("unused")
        override suspend fun addMeal(planId: String, request: AddMealRequest): Any = error("unused")
        override suspend fun getRecipes(query: RecipeQuery?): List<Recipe> = error("unused")
    }

    private val repository = FakeDietary()
    private val viewModel = MealPlanDetailViewModel(repository)

    private fun meal(id: String, date: String, type: String) = PlanMeal(
        id = id,
        planId = "p1",
        recipeId = "r-$id",
        recipeName = "Recipe $id",
        mealType = type,
        scheduledDate = date,
        calories = 400,
    )

    private fun plan(vararg meals: PlanMeal) = MealPlan(
        id = "p1",
        name = "Plan p1",
        userId = "user-1",
        startDate = "2026-10-01",
        endDate = "2026-10-07",
        meals = meals.toList(),
        status = "ACTIVE",
    )

    @Test
    fun `starts in the loading state`() {
        assertTrue(viewModel.state.value.isLoading)
        assertNull(viewModel.state.value.plan)
    }

    @Test
    fun `load shows the plan grouped by day and meal type`() = runTest {
        repository.plan = plan(
            meal("2", "2026-10-02", "LUNCH"),
            meal("1", "2026-10-01", "DINNER"),
            meal("3", "2026-10-01", "BREAKFAST"),
        )

        viewModel.load("p1")

        val state = viewModel.state.value
        assertEquals("p1", repository.requested)
        assertEquals("Plan p1", state.plan?.name)
        assertEquals(listOf("2026-10-01", "2026-10-02"), state.days.map { it.date })
        assertEquals(listOf("BREAKFAST", "DINNER"), state.days.first().sections.map { it.mealType })
        assertFalse(state.isLoading)
        assertNull(state.error)
    }

    @Test
    fun `a plan without meals is flagged, not treated as an error`() = runTest {
        repository.plan = plan()

        viewModel.load("p1")

        assertTrue(viewModel.state.value.hasNoMeals)
        assertNull(viewModel.state.value.error)
    }

    @Test
    fun `failures map to localizable error codes`() = runTest {
        suspend fun errorFor(failure: Throwable): MealPlanDetailError? {
            val vm = MealPlanDetailViewModel(FakeDietary().apply { this.failure = failure })
            vm.load("p1")
            return vm.state.value.error
        }

        assertEquals(MealPlanDetailError.NETWORK, errorFor(ApiException.NetworkError()))
        assertEquals(MealPlanDetailError.SERVER_PROBLEM, errorFor(ApiException.HttpError(502, null)))
        assertEquals(MealPlanDetailError.SESSION_EXPIRED, errorFor(ApiException.HttpError(401, null)))
        assertEquals(MealPlanDetailError.NOT_FOUND, errorFor(ApiException.HttpError(404, null)))
        assertEquals(MealPlanDetailError.UNKNOWN, errorFor(ApiException.HttpError(418, null)))
        assertEquals(MealPlanDetailError.UNKNOWN, errorFor(IllegalStateException("boom")))
    }

    @Test
    fun `a failed first load has an error and no plan`() = runTest {
        repository.failure = ApiException.NetworkError()

        viewModel.load("p1")

        val state = viewModel.state.value
        assertNull(state.plan)
        assertFalse(state.isLoading)
        assertEquals(MealPlanDetailError.NETWORK, state.error)
    }

    @Test
    fun `retry after a failure recovers`() = runTest {
        repository.failure = ApiException.NetworkError()
        viewModel.load("p1")

        repository.failure = null
        repository.plan = plan(meal("1", "2026-10-01", "LUNCH"))
        viewModel.load("p1")

        assertNotNull(viewModel.state.value.plan)
        assertNull(viewModel.state.value.error)
        assertEquals(1, viewModel.state.value.days.size)
    }

    @Test
    fun `refresh keeps the plan visible while it runs`() = runTest {
        repository.plan = plan(meal("1", "2026-10-01", "LUNCH"))
        viewModel.load("p1")

        repository.gate = CompletableDeferred()
        repository.plan = plan(meal("1", "2026-10-01", "LUNCH"), meal("2", "2026-10-02", "LUNCH"))
        val refreshing = launch { viewModel.refresh() }
        testScheduler.advanceUntilIdle()

        assertTrue(viewModel.state.value.isRefreshing)
        assertEquals(1, viewModel.state.value.days.size)

        repository.gate!!.complete(Unit)
        refreshing.join()

        assertFalse(viewModel.state.value.isRefreshing)
        assertEquals(2, viewModel.state.value.days.size)
    }

    @Test
    fun `a failed refresh keeps the old plan and reports the error`() = runTest {
        repository.plan = plan(meal("1", "2026-10-01", "LUNCH"))
        viewModel.load("p1")

        repository.failure = ApiException.NetworkError()
        viewModel.refresh()

        val state = viewModel.state.value
        assertEquals(1, state.days.size)
        assertEquals(MealPlanDetailError.NETWORK, state.error)
        assertFalse(state.isRefreshing)
    }

    @Test
    fun `a plan deleted elsewhere is removed from the screen, not kept as current`() = runTest {
        repository.plan = plan(meal("1", "2026-10-01", "LUNCH"))
        viewModel.load("p1")

        repository.plan = null
        viewModel.refresh()

        val state = viewModel.state.value
        assertEquals(MealPlanDetailError.NOT_FOUND, state.error)
        assertNull(state.plan)
        assertEquals(emptyList(), state.days)
    }

    @Test
    fun `refresh before any load does nothing`() = runTest {
        viewModel.refresh()

        assertNull(repository.requested)
        assertTrue(viewModel.state.value.isLoading)
    }

    @Test
    fun `cancelling a load clears the loading flags`() = runTest {
        repository.gate = CompletableDeferred()
        val job = launch { viewModel.load("p1") }
        testScheduler.advanceUntilIdle()
        assertTrue(viewModel.state.value.isLoading)

        job.cancel()
        job.join()

        assertFalse(viewModel.state.value.isLoading)
        assertNull(viewModel.state.value.error)
    }
}
