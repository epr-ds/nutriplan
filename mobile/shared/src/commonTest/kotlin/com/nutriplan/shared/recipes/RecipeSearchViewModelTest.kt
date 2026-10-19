package com.nutriplan.shared.recipes

import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.UpdateMealRequest
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
import kotlin.test.assertNull
import kotlin.test.assertTrue

class RecipeSearchViewModelTest {

    private class FakeDietary : DietaryRepository {
        val queries = mutableListOf<RecipeSearchQuery>()
        var respond: (RecipeSearchQuery) -> List<Recipe> = { emptyList() }
        var failure: Throwable? = null

        /** Consumed by the next call: that call waits until it is completed. */
        var nextGate: CompletableDeferred<Unit>? = null

        override suspend fun searchRecipes(query: RecipeSearchQuery): List<Recipe> {
            queries += query
            val result = respond(query)
            val gate = nextGate
            nextGate = null
            gate?.await()
            failure?.let { throw it }
            return result
        }

        override suspend fun getRecipe(recipeId: String): Recipe = error("unused")
        override suspend fun getNutritionDisclaimer(): NutritionDisclaimer = error("unused")
        override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlanSummary> = error("unused")
        override suspend fun getMealPlan(planId: String): MealPlan = error("unused")
        override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan = error("unused")
        override suspend fun updateMealPlanStatus(planId: String, status: String): MealPlan = error("unused")
        override suspend fun removeMeal(planId: String, mealId: String): Unit = error("unused")
        override suspend fun updateMeal(planId: String, mealId: String, request: UpdateMealRequest): PlanMeal = error("unused")
        override suspend fun addMeal(planId: String, request: AddMealRequest): PlanMeal = error("unused")
    }

    private val repository = FakeDietary()
    private val viewModel = RecipeSearchViewModel(repository)

    private fun recipe(id: String) = Recipe(id = id, name = "Recipe $id")

    private fun page(prefix: String, size: Int) = List(size) { recipe("$prefix$it") }

    // --- filters ---

    @Test
    fun `starts idle with no filters`() {
        val state = viewModel.state.value

        assertFalse(state.hasFilters)
        assertFalse(state.hasSearched)
        assertFalse(state.isLoading)
        assertFalse(state.isEmptyResult)
    }

    @Test
    fun `search sends the filters from the first page`() = runTest {
        viewModel.onIngredientsChange("  Chicken , olive oil;rice\nchicken ,, ")
        viewModel.onDietTypeChange("keto")
        viewModel.onMaxCaloriesChange("600")
        viewModel.onMinProteinChange("30.5")

        viewModel.search()

        assertEquals(
            RecipeSearchQuery(
                ingredients = listOf("Chicken", "olive oil", "rice"),
                dietType = "keto",
                maxCalories = 600,
                minProtein = 30.5,
                page = 1,
                limit = 20,
            ),
            repository.queries.single(),
        )
    }

    @Test
    fun `a search without filters browses the catalog`() = runTest {
        viewModel.search()

        assertEquals(RecipeSearchQuery(), repository.queries.single())
    }

    @Test
    fun `number fields keep only valid characters`() {
        viewModel.onMaxCaloriesChange("6a0,0kcal")
        viewModel.onMinProteinChange("3.0.5g")

        assertEquals("600", viewModel.state.value.maxCalories)
        assertEquals("3.05", viewModel.state.value.minProtein)

        viewModel.onMaxCaloriesChange("1234567")
        assertEquals("12345", viewModel.state.value.maxCalories)
    }

    @Test
    fun `a lone decimal point is not a protein value`() = runTest {
        viewModel.onMinProteinChange(".")

        viewModel.search()

        assertNull(repository.queries.single().minProtein)
    }

    @Test
    fun `an unknown diet type is ignored and a known one can be cleared`() {
        viewModel.onDietTypeChange("carnivore")
        assertNull(viewModel.state.value.dietType)

        viewModel.onDietTypeChange("vegan")
        assertEquals("vegan", viewModel.state.value.dietType)

        viewModel.onDietTypeChange(null)
        assertNull(viewModel.state.value.dietType)
    }

    @Test
    fun `clearing the filters resets them but keeps the results`() = runTest {
        repository.respond = { listOf(recipe("a")) }
        viewModel.onIngredientsChange("rice")
        viewModel.search()

        viewModel.clearFilters()

        assertFalse(viewModel.state.value.hasFilters)
        assertEquals(listOf("a"), viewModel.state.value.recipes.map { it.id })
    }

    // --- results ---

    @Test
    fun `a full page means there may be more`() = runTest {
        repository.respond = { page("p", 20) }

        viewModel.search()

        assertEquals(20, viewModel.state.value.recipes.size)
        assertTrue(viewModel.state.value.hasMore)
    }

    @Test
    fun `a short page is the last one`() = runTest {
        repository.respond = { page("p", 7) }

        viewModel.search()

        assertFalse(viewModel.state.value.hasMore)
    }

    @Test
    fun `no results is flagged as an empty result, not an error`() = runTest {
        viewModel.search()

        val state = viewModel.state.value
        assertTrue(state.isEmptyResult)
        assertNull(state.error)
    }

    @Test
    fun `load more appends the next page of the same search`() = runTest {
        repository.respond = { query -> if (query.page == 1) page("a", 20) else page("b", 5) }
        viewModel.onIngredientsChange("rice")
        viewModel.search()

        viewModel.loadMore()

        assertEquals(25, viewModel.state.value.recipes.size)
        assertEquals(listOf(1, 2), repository.queries.map { it.page })
        assertEquals(listOf("rice"), repository.queries.last().ingredients)
        assertFalse(viewModel.state.value.hasMore)
    }

    @Test
    fun `load more uses the filters that were searched, not ones edited since`() = runTest {
        repository.respond = { page("a", 20) }
        viewModel.onIngredientsChange("rice")
        viewModel.search()

        viewModel.onIngredientsChange("beans")
        viewModel.onDietTypeChange("vegan")
        viewModel.loadMore()

        val second = repository.queries.last()
        assertEquals(listOf("rice"), second.ingredients)
        assertNull(second.dietType)
        assertEquals(2, second.page)
    }

    @Test
    fun `load more skips recipes it already has`() = runTest {
        repository.respond = { query -> if (query.page == 1) page("a", 20) else listOf(recipe("a0"), recipe("new")) }
        viewModel.search()

        viewModel.loadMore()

        val ids = viewModel.state.value.recipes.map { it.id }
        assertEquals(21, ids.size)
        assertEquals(1, ids.count { it == "a0" })
    }

    @Test
    fun `load more does nothing when there is no more or a request is running`() = runTest {
        repository.respond = { page("a", 3) }
        viewModel.search()
        viewModel.loadMore()
        assertEquals(1, repository.queries.size)

        repository.respond = { page("a", 20) }
        viewModel.search()
        repository.nextGate = CompletableDeferred()
        val first = launch { viewModel.loadMore() }
        testScheduler.advanceUntilIdle()
        viewModel.loadMore()

        assertEquals(3, repository.queries.size, "search, search, and exactly one load more")
        repository.nextGate = null
        first.cancel()
    }

    // --- failures ---

    @Test
    fun `a failed search drops the old results and reports the error`() = runTest {
        repository.respond = { listOf(recipe("old")) }
        viewModel.search()

        repository.failure = ApiException.NetworkError()
        viewModel.search()

        val state = viewModel.state.value
        assertEquals(RecipeListError.NETWORK, state.error)
        assertEquals(emptyList(), state.recipes)
        assertFalse(state.isEmptyResult)
        assertFalse(state.isLoading)
    }

    @Test
    fun `failures map to localizable error codes`() = runTest {
        suspend fun errorFor(failure: Throwable): RecipeListError? {
            val vm = RecipeSearchViewModel(FakeDietary().apply { this.failure = failure })
            vm.search()
            return vm.state.value.error
        }

        assertEquals(RecipeListError.NETWORK, errorFor(ApiException.NetworkError()))
        assertEquals(RecipeListError.SERVER_PROBLEM, errorFor(ApiException.HttpError(500, null)))
        assertEquals(RecipeListError.SESSION_EXPIRED, errorFor(ApiException.HttpError(401, null)))
        assertEquals(
            RecipeListError.SESSION_EXPIRED,
            errorFor(ApiException.create("Unauthorized", ApiException.Code.UNAUTHORIZED)),
        )
        assertEquals(RecipeListError.UNKNOWN, errorFor(ApiException.HttpError(422, null)))
        assertEquals(RecipeListError.UNKNOWN, errorFor(IllegalStateException("boom")))
    }

    @Test
    fun `a failed load more keeps the list and allows a retry`() = runTest {
        repository.respond = { query -> if (query.page == 1) page("a", 20) else page("b", 4) }
        viewModel.search()

        repository.failure = ApiException.NetworkError()
        viewModel.loadMore()
        assertEquals(20, viewModel.state.value.recipes.size)
        assertEquals(RecipeListError.NETWORK, viewModel.state.value.error)
        assertTrue(viewModel.state.value.hasMore)
        assertFalse(viewModel.state.value.isLoadingMore)

        repository.failure = null
        viewModel.loadMore()
        assertEquals(24, viewModel.state.value.recipes.size)
        assertNull(viewModel.state.value.error)
    }

    // --- concurrency ---

    @Test
    fun `a slow older search never overwrites newer results`() = runTest {
        repository.respond = { query -> listOf(recipe(query.ingredients.firstOrNull() ?: "none")) }

        viewModel.onIngredientsChange("slow")
        repository.nextGate = CompletableDeferred()
        val gate = repository.nextGate!!
        val slow = launch { viewModel.search() }
        testScheduler.advanceUntilIdle()

        viewModel.onIngredientsChange("fast")
        viewModel.search()
        assertEquals(listOf("fast"), viewModel.state.value.recipes.map { it.id })

        gate.complete(Unit)
        slow.join()

        assertEquals(listOf("fast"), viewModel.state.value.recipes.map { it.id })
        assertFalse(viewModel.state.value.isLoading)
    }

    @Test
    fun `cancelling a search clears the loading flag`() = runTest {
        repository.nextGate = CompletableDeferred()
        val job = launch { viewModel.search() }
        testScheduler.advanceUntilIdle()
        assertTrue(viewModel.state.value.isLoading)

        job.cancel()
        job.join()

        assertFalse(viewModel.state.value.isLoading)
        assertNull(viewModel.state.value.error)
    }
}
