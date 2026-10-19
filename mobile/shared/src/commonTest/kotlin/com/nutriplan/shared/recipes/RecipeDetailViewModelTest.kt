package com.nutriplan.shared.recipes

import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.MealPlanQuery
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.data.model.NutritionDisclaimer
import com.nutriplan.shared.data.model.PlanMeal
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
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class RecipeDetailViewModelTest {

    private class FakeDietary : DietaryRepository {
        var recipe: Recipe? = Recipe(id = "r1", name = "Soup")
        var recipeFailure: Throwable? = null
        var disclaimer: NutritionDisclaimer? = NutritionDisclaimer(disclaimer = "Estimates only.")
        var disclaimerFailure: Throwable? = null
        var gate: CompletableDeferred<Unit>? = null
        var recipeCalls = 0
        var disclaimerCalls = 0
        var requested: String? = null

        override suspend fun getRecipe(recipeId: String): Recipe {
            recipeCalls++
            requested = recipeId
            gate?.await()
            recipeFailure?.let { throw it }
            return recipe ?: throw ApiException.HttpError(404, null)
        }

        override suspend fun getNutritionDisclaimer(): NutritionDisclaimer {
            disclaimerCalls++
            disclaimerFailure?.let { throw it }
            return disclaimer!!
        }

        override suspend fun searchRecipes(query: RecipeSearchQuery): List<Recipe> = error("unused")
        override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlanSummary> = error("unused")
        override suspend fun getMealPlan(planId: String): MealPlan = error("unused")
        override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan = error("unused")
        override suspend fun updateMealPlanStatus(planId: String, status: String): MealPlan = error("unused")
        override suspend fun addMeal(planId: String, request: AddMealRequest): PlanMeal = error("unused")
    }

    private val repository = FakeDietary()
    private val viewModel = RecipeDetailViewModel(repository)

    @Test
    fun `starts in the loading state`() {
        assertTrue(viewModel.state.value.isLoading)
        assertNull(viewModel.state.value.recipe)
    }

    @Test
    fun `load shows the recipe and the server's disclaimer`() = runTest {
        viewModel.load("r1")

        val state = viewModel.state.value
        assertEquals("r1", repository.requested)
        assertEquals("Soup", state.recipe?.name)
        assertEquals("Estimates only.", state.disclaimer?.disclaimer)
        assertFalse(state.isLoading)
        assertNull(state.error)
    }

    @Test
    fun `a disclaimer that cannot be loaded does not hide the recipe`() = runTest {
        repository.disclaimerFailure = ApiException.NetworkError()

        viewModel.load("r1")

        val state = viewModel.state.value
        assertNotNull(state.recipe)
        assertNull(state.disclaimer)
        assertNull(state.error)
    }

    @Test
    fun `the disclaimer is fetched once, even across retries`() = runTest {
        viewModel.load("r1")
        viewModel.load("r1")

        assertEquals(1, repository.disclaimerCalls)
        assertEquals(2, repository.recipeCalls)
    }

    @Test
    fun `a missing disclaimer is tried again on the next load`() = runTest {
        repository.disclaimerFailure = ApiException.NetworkError()
        viewModel.load("r1")

        repository.disclaimerFailure = null
        viewModel.load("r1")

        assertEquals("Estimates only.", viewModel.state.value.disclaimer?.disclaimer)
    }

    @Test
    fun `failures map to localizable error codes`() = runTest {
        suspend fun errorFor(failure: Throwable): RecipeDetailError? {
            val vm = RecipeDetailViewModel(FakeDietary().apply { recipeFailure = failure })
            vm.load("r1")
            return vm.state.value.error
        }

        assertEquals(RecipeDetailError.NETWORK, errorFor(ApiException.NetworkError()))
        assertEquals(RecipeDetailError.SERVER_PROBLEM, errorFor(ApiException.HttpError(503, null)))
        assertEquals(RecipeDetailError.SESSION_EXPIRED, errorFor(ApiException.HttpError(401, null)))
        assertEquals(RecipeDetailError.NOT_FOUND, errorFor(ApiException.HttpError(404, null)))
        assertEquals(
            RecipeDetailError.NOT_FOUND,
            errorFor(ApiException.create("Not found", ApiException.Code.NOT_FOUND)),
        )
        assertEquals(RecipeDetailError.UNKNOWN, errorFor(ApiException.HttpError(418, null)))
        assertEquals(RecipeDetailError.UNKNOWN, errorFor(IllegalStateException("boom")))
    }

    @Test
    fun `a failed load has an error, no recipe and no disclaimer request`() = runTest {
        repository.recipeFailure = ApiException.NetworkError()

        viewModel.load("r1")

        val state = viewModel.state.value
        assertNull(state.recipe)
        assertFalse(state.isLoading)
        assertEquals(RecipeDetailError.NETWORK, state.error)
        assertEquals(0, repository.disclaimerCalls)
    }

    @Test
    fun `retry after a failure recovers`() = runTest {
        repository.recipeFailure = ApiException.NetworkError()
        viewModel.load("r1")

        repository.recipeFailure = null
        viewModel.load("r1")

        assertNotNull(viewModel.state.value.recipe)
        assertNull(viewModel.state.value.error)
    }

    @Test
    fun `cancelling a load clears the loading flag`() = runTest {
        repository.gate = CompletableDeferred()
        val job = launch { viewModel.load("r1") }
        testScheduler.advanceUntilIdle()
        assertTrue(viewModel.state.value.isLoading)

        job.cancel()
        job.join()

        assertFalse(viewModel.state.value.isLoading)
        assertNull(viewModel.state.value.error)
    }
}
