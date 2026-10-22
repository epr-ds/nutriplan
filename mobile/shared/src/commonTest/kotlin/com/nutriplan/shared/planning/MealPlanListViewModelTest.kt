package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.UpdateMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.MealPlanQuery
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.NutritionDisclaimer
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.model.RecipeSearchQuery
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.repository.DietaryRepository
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class MealPlanListViewModelTest {

    private class FakeDietary : DietaryRepository {
        var plans: List<MealPlanSummary> = emptyList()
        var failure: Throwable? = null
        var gate: CompletableDeferred<Unit>? = null

        override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlanSummary> {
            gate?.await()
            failure?.let { throw it }
            return plans
        }

        override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan = error("unused")
        override suspend fun getMealPlan(planId: String): MealPlan = error("unused")
        override suspend fun updateMealPlanStatus(planId: String, status: String): MealPlan = error("unused")
        override suspend fun removeMeal(planId: String, mealId: String): Unit = error("unused")
        override suspend fun updateMeal(planId: String, mealId: String, request: UpdateMealRequest): PlanMeal = error("unused")
        override suspend fun addMeal(planId: String, request: AddMealRequest): PlanMeal = error("unused")
        override suspend fun searchRecipes(query: RecipeSearchQuery): List<Recipe> = error("unused")
        override suspend fun getRecipe(recipeId: String): Recipe = error("unused")
        override suspend fun getNutritionDisclaimer(): NutritionDisclaimer = error("unused")
    }

    private val repository = FakeDietary()
    private val viewModel = MealPlanListViewModel(repository)

    private fun plan(id: String) = MealPlanSummary(
        id = id,
        name = "Plan $id",
        startDate = "2026-10-01",
        endDate = "2026-10-07",
        status = "active",
    )

    @Test
    fun `starts in the loading state`() {
        assertTrue(viewModel.state.value.isLoading)
        assertFalse(viewModel.state.value.isEmpty)
    }

    @Test
    fun `load shows the plans`() = runTest {
        repository.plans = listOf(plan("a"), plan("b"))

        viewModel.load()

        val state = viewModel.state.value
        assertEquals(listOf("a", "b"), state.plans.map { it.id })
        assertFalse(state.isLoading)
        assertNull(state.error)
    }

    @Test
    fun `no plans is the empty state not an error`() = runTest {
        viewModel.load()

        assertTrue(viewModel.state.value.isEmpty)
        assertNull(viewModel.state.value.error)
    }

    @Test
    fun `failures map to localizable error codes`() = runTest {
        suspend fun errorFor(failure: Throwable): MealPlanListError? {
            val vm = MealPlanListViewModel(FakeDietary().apply { this.failure = failure })
            vm.load()
            return vm.state.value.error
        }

        assertEquals(MealPlanListError.NETWORK, errorFor(ApiException.NetworkError()))
        assertEquals(MealPlanListError.SERVER_PROBLEM, errorFor(ApiException.HttpError(503, null)))
        assertEquals(MealPlanListError.SESSION_EXPIRED, errorFor(ApiException.HttpError(401, null)))
        assertEquals(MealPlanListError.UNKNOWN, errorFor(ApiException.HttpError(404, null)))
        assertEquals(MealPlanListError.UNKNOWN, errorFor(IllegalStateException("boom")))
    }

    @Test
    fun `a 401 reported through the repositories' create helper is a session problem not offline`() = runTest {
        // The repositories used to throw ApiException.create(..., UNAUTHORIZED), a NetworkError by class.
        suspend fun errorFor(failure: Throwable): MealPlanListError? {
            val vm = MealPlanListViewModel(FakeDietary().apply { this.failure = failure })
            vm.load()
            return vm.state.value.error
        }

        assertEquals(
            MealPlanListError.SESSION_EXPIRED,
            errorFor(ApiException.create("Unauthorized", ApiException.Code.UNAUTHORIZED)),
        )
        assertEquals(
            MealPlanListError.NETWORK,
            errorFor(ApiException.create("offline", ApiException.Code.NETWORK_ERROR)),
        )
    }

    @Test
    fun `a failed first load is not shown as empty`() = runTest {
        repository.failure = ApiException.NetworkError()

        viewModel.load()

        val state = viewModel.state.value
        assertFalse(state.isLoading)
        assertFalse(state.isEmpty)
        assertEquals(MealPlanListError.NETWORK, state.error)
    }

    @Test
    fun `retry after a failure recovers`() = runTest {
        repository.failure = ApiException.NetworkError()
        viewModel.load()

        repository.failure = null
        repository.plans = listOf(plan("a"))
        viewModel.load()

        assertEquals(listOf("a"), viewModel.state.value.plans.map { it.id })
        assertNull(viewModel.state.value.error)
    }

    @Test
    fun `refresh keeps the plans visible while it runs`() = runTest {
        repository.plans = listOf(plan("a"))
        viewModel.load()

        repository.gate = CompletableDeferred()
        repository.plans = listOf(plan("a"), plan("b"))
        val refreshing = launch { viewModel.refresh() }
        testScheduler.advanceUntilIdle()

        assertTrue(viewModel.state.value.isRefreshing)
        assertEquals(listOf("a"), viewModel.state.value.plans.map { it.id })

        repository.gate!!.complete(Unit)
        refreshing.join()

        assertFalse(viewModel.state.value.isRefreshing)
        assertEquals(listOf("a", "b"), viewModel.state.value.plans.map { it.id })
    }

    @Test
    fun `a failed refresh keeps the old plans and reports the error`() = runTest {
        repository.plans = listOf(plan("a"))
        viewModel.load()

        repository.failure = ApiException.NetworkError()
        viewModel.refresh()

        val state = viewModel.state.value
        assertEquals(listOf("a"), state.plans.map { it.id })
        assertEquals(MealPlanListError.NETWORK, state.error)
        assertFalse(state.isRefreshing)
    }

    @Test
    fun `cancelling a load rethrows and clears the loading flags`() = runTest {
        repository.gate = CompletableDeferred()
        val job = launch { viewModel.load() }
        testScheduler.advanceUntilIdle()
        assertTrue(viewModel.state.value.isLoading)

        job.cancel()
        job.join()

        assertFalse(viewModel.state.value.isLoading)
        assertNull(viewModel.state.value.error)
    }
}
