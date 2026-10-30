package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.MealPlanQuery
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.data.model.NutritionDisclaimer
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.model.RecipeSearchQuery
import com.nutriplan.shared.data.model.UpdateMealRequest
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

class AddMealViewModelTest {

    private class FakeDietary : DietaryRepository {
        var recipe: Recipe = Recipe(id = "r1", name = "Soup")
        var recipeFailure: Throwable? = null
        var plan: MealPlan? = MealPlan(
            id = "p1",
            name = "Week",
            startDate = "2026-10-01",
            endDate = "2026-10-03",
            dailyCalorieTarget = 2000,
            status = "draft",
        )
        var planFailure: Throwable? = null
        var addFailure: Throwable? = null
        var updateFailure: Throwable? = null
        var addGate: CompletableDeferred<Unit>? = null

        val added = mutableListOf<Pair<String, AddMealRequest>>()
        val updated = mutableListOf<Triple<String, String, UpdateMealRequest>>()

        override suspend fun getRecipe(recipeId: String): Recipe {
            recipeFailure?.let { throw it }
            return recipe
        }

        override suspend fun getMealPlan(planId: String): MealPlan {
            planFailure?.let { throw it }
            return plan!!
        }

        override suspend fun addMeal(planId: String, request: AddMealRequest): PlanMeal {
            added += planId to request
            addGate?.await()
            addFailure?.let { throw it }
            return PlanMeal(id = "m${added.size}", mealType = request.mealType, servings = request.servings)
        }

        override suspend fun removeMeal(planId: String, mealId: String): Unit = error("unused")
        override suspend fun updateMeal(planId: String, mealId: String, request: UpdateMealRequest): PlanMeal {
            updated += Triple(planId, mealId, request)
            updateFailure?.let { throw it }
            return PlanMeal(id = mealId, mealType = "lunch", servings = 1.0, dayIndex = request.dayIndex)
        }

        override suspend fun searchRecipes(query: RecipeSearchQuery): List<Recipe> = error("unused")
        override suspend fun getNutritionDisclaimer(): NutritionDisclaimer = error("unused")
        override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlanSummary> = error("unused")
        override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan = error("unused")
        override suspend fun updateMealPlanStatus(planId: String, status: String): MealPlan = error("unused")
    }

    private val repository = FakeDietary()
    private val viewModel = AddMealViewModel(repository)

    private suspend fun started() = viewModel.start("p1", "r1")

    // --- loading ---

    @Test
    fun `starts in the loading state with sensible defaults`() {
        val state = viewModel.state.value

        assertTrue(state.isLoading)
        assertEquals("1", state.servings)
        assertNull(state.mealType)
        assertNull(state.dayIndex)
    }

    // --- current state ---

    @Test
    fun `the add meal form exposes its current state`() = runTest {
        val state = viewModel.currentState()

        assertTrue(state.isLoading)
        assertEquals("1", state.servings)
        assertNull(state.mealType)
    }

    @Test
    fun `the current state is the latest one`() = runTest {
        started()

        viewModel.onMealTypeChange("dinner")
        viewModel.onServingsChange("2")
        viewModel.onDayChange(1)

        val state = viewModel.currentState()
        assertEquals("Soup", state.recipe?.name)
        assertEquals("dinner", state.mealType)
        assertEquals("2", state.servings)
        assertEquals(1, state.dayIndex)
        assertFalse(state.isLoading)
    }

    @Test
    fun `start loads the recipe and one option per day of the plan`() = runTest {
        started()

        val state = viewModel.state.value
        assertEquals("Soup", state.recipe?.name)
        assertFalse(state.isLoading)
        assertEquals(
            listOf(PlanDayOption(0, "2026-10-01"), PlanDayOption(1, "2026-10-02"), PlanDayOption(2, "2026-10-03")),
            state.days,
        )
    }

    @Test
    fun `a plan spanning a month end lists every date`() = runTest {
        repository.plan = repository.plan!!.copy(startDate = "2026-02-27", endDate = "2026-03-01")

        started()

        assertEquals(listOf("2026-02-27", "2026-02-28", "2026-03-01"), viewModel.state.value.days.map { it.date })
    }

    @Test
    fun `a plan that cannot be loaded does not block the form`() = runTest {
        repository.planFailure = ApiException.NetworkError()

        started()

        val state = viewModel.state.value
        assertNotNull(state.recipe)
        assertTrue(state.days.isEmpty())
        assertNull(state.loadError)
    }

    @Test
    fun `a recipe that cannot be loaded is reported and can be retried`() = runTest {
        repository.recipeFailure = ApiException.NetworkError()
        started()
        assertEquals(AddMealError.NETWORK, viewModel.state.value.loadError)
        assertFalse(viewModel.state.value.isLoading)

        repository.recipeFailure = null
        started()

        assertNull(viewModel.state.value.loadError)
        assertEquals("Soup", viewModel.state.value.recipe?.name)
    }

    @Test
    fun `load failures map to stable codes`() = runTest {
        suspend fun errorFor(failure: Throwable): AddMealError? {
            repository.recipeFailure = failure
            val vm = AddMealViewModel(repository)
            vm.start("p1", "r1")
            return vm.state.value.loadError
        }

        assertEquals(AddMealError.NOT_FOUND, errorFor(ApiException.HttpError(404, null)))
        assertEquals(AddMealError.SESSION_EXPIRED, errorFor(ApiException.HttpError(401, null)))
        assertEquals(AddMealError.SERVER_PROBLEM, errorFor(ApiException.HttpError(503, null)))
        assertEquals(AddMealError.UNKNOWN, errorFor(ApiException.HttpError(418, null)))
    }

    // --- fields ---

    @Test
    fun `only the API's meal types are accepted`() = runTest {
        started()

        viewModel.onMealTypeChange("brunch")
        assertNull(viewModel.state.value.mealType)

        viewModel.onMealTypeChange("dinner")
        assertEquals("dinner", viewModel.state.value.mealType)
    }

    @Test
    fun `servings keep digits and one decimal point`() {
        viewModel.onServingsChange("1,5x.2.5")

        assertEquals("15.25", viewModel.state.value.servings)
    }

    @Test
    fun `only a day of the plan can be chosen`() = runTest {
        started()

        viewModel.onDayChange(7)
        assertNull(viewModel.state.value.dayIndex)

        viewModel.onDayChange(1)
        assertEquals(1, viewModel.state.value.dayIndex)

        viewModel.onDayChange(null)
        assertNull(viewModel.state.value.dayIndex)
    }

    // --- validation ---

    @Test
    fun `saving without a meal type asks for one and sends nothing`() = runTest {
        started()

        viewModel.save()

        assertEquals(AddMealFieldError.MEAL_TYPE_REQUIRED, viewModel.state.value.mealTypeError)
        assertTrue(repository.added.isEmpty())
    }

    @Test
    fun `servings must be a positive number`() = runTest {
        started()
        viewModel.onMealTypeChange("lunch")

        suspend fun check(text: String, expected: AddMealFieldError) {
            viewModel.onServingsChange(text)
            viewModel.save()
            assertEquals(expected, viewModel.state.value.servingsError, "servings '$text'")
        }
        check("", AddMealFieldError.SERVINGS_REQUIRED)
        check("0", AddMealFieldError.SERVINGS_INVALID)
        check(".", AddMealFieldError.SERVINGS_INVALID)
        check("100", AddMealFieldError.SERVINGS_INVALID)
        assertTrue(repository.added.isEmpty())
    }

    @Test
    fun `editing a field clears its error`() = runTest {
        started()
        viewModel.save()
        assertNotNull(viewModel.state.value.mealTypeError)

        viewModel.onMealTypeChange("lunch")

        assertNull(viewModel.state.value.mealTypeError)
    }

    // --- saving ---

    @Test
    fun `save adds the meal with the chosen type and servings and finishes`() = runTest {
        started()
        viewModel.onMealTypeChange("dinner")
        viewModel.onServingsChange("1.5")

        viewModel.save()

        assertEquals(listOf("p1" to AddMealRequest("dinner", "r1", 1.5)), repository.added)
        assertTrue(repository.updated.isEmpty(), "no day was chosen")
        assertTrue(viewModel.state.value.isDone)
        assertFalse(viewModel.state.value.isSaving)
    }

    @Test
    fun `a chosen day is set on the new meal`() = runTest {
        started()
        viewModel.onMealTypeChange("lunch")
        viewModel.onDayChange(2)

        viewModel.save()

        assertEquals(listOf(Triple("p1", "m1", UpdateMealRequest(dayIndex = 2))), repository.updated)
        assertTrue(viewModel.state.value.isDone)
    }

    @Test
    fun `a failed add keeps the form and can be retried`() = runTest {
        started()
        viewModel.onMealTypeChange("lunch")
        repository.addFailure = ApiException.NetworkError()

        viewModel.save()
        assertEquals(AddMealError.NETWORK, viewModel.state.value.error)
        assertNull(viewModel.state.value.addedMealId)
        assertFalse(viewModel.state.value.isDone)

        repository.addFailure = null
        viewModel.save()

        assertTrue(viewModel.state.value.isDone)
        assertNull(viewModel.state.value.error)
    }

    @Test
    fun `save failures map to stable codes`() = runTest {
        suspend fun errorFor(failure: Throwable): AddMealError? {
            val fake = FakeDietary().apply { addFailure = failure }
            val vm = AddMealViewModel(fake)
            vm.start("p1", "r1")
            vm.onMealTypeChange("lunch")
            vm.save()
            return vm.state.value.error
        }

        assertEquals(AddMealError.NETWORK, errorFor(ApiException.NetworkError()))
        assertEquals(AddMealError.SESSION_EXPIRED, errorFor(ApiException.HttpError(401, null)))
        assertEquals(AddMealError.NOT_FOUND, errorFor(ApiException.HttpError(404, null)))
        assertEquals(AddMealError.REJECTED, errorFor(ApiException.HttpError(422, null)))
        assertEquals(AddMealError.SERVER_PROBLEM, errorFor(ApiException.HttpError(500, null)))
    }

    @Test
    fun `if only the day fails the meal is kept and a retry sets just the day`() = runTest {
        started()
        viewModel.onMealTypeChange("lunch")
        viewModel.onDayChange(1)
        repository.updateFailure = ApiException.NetworkError()

        viewModel.save()

        val failed = viewModel.state.value
        assertEquals("m1", failed.addedMealId)
        assertEquals(AddMealError.NETWORK, failed.error)
        assertTrue(failed.dayNotSet)
        assertFalse(failed.isDone)

        repository.updateFailure = null
        viewModel.save()

        assertEquals(1, repository.added.size, "the meal must not be added twice")
        assertEquals(2, repository.updated.size)
        assertTrue(viewModel.state.value.isDone)
        assertFalse(viewModel.state.value.dayNotSet)
    }

    @Test
    fun `after the meal exists its type and servings are locked but the day can change`() = runTest {
        started()
        viewModel.onMealTypeChange("lunch")
        viewModel.onDayChange(1)
        repository.updateFailure = ApiException.NetworkError()
        viewModel.save()

        viewModel.onMealTypeChange("dinner")
        viewModel.onServingsChange("9")
        viewModel.onDayChange(2)

        val state = viewModel.state.value
        assertEquals("lunch", state.mealType)
        assertEquals("1", state.servings)
        assertEquals(2, state.dayIndex)
        assertTrue(state.dayNotSet, "the retry stays offered after picking another day")

        repository.updateFailure = null
        viewModel.save()
        assertEquals(UpdateMealRequest(dayIndex = 2), repository.updated.last().third)
    }

    @Test
    fun `a second save while one is running is ignored`() = runTest {
        started()
        viewModel.onMealTypeChange("lunch")
        val gate = CompletableDeferred<Unit>()
        repository.addGate = gate

        val first = launch { viewModel.save() }
        testScheduler.advanceUntilIdle()
        viewModel.save()
        gate.complete(Unit)
        first.join()

        assertEquals(1, repository.added.size)
    }

    @Test
    fun `nothing happens once finished`() = runTest {
        started()
        viewModel.onMealTypeChange("lunch")
        viewModel.save()

        viewModel.save()

        assertEquals(1, repository.added.size)
    }

    @Test
    fun `cancelling a save rethrows and clears the saving flag`() = runTest {
        started()
        viewModel.onMealTypeChange("lunch")
        repository.addGate = CompletableDeferred()

        val job = launch { viewModel.save() }
        testScheduler.advanceUntilIdle()
        assertTrue(viewModel.state.value.isSaving)
        job.cancel()
        job.join()

        assertFalse(viewModel.state.value.isSaving)
        assertNull(viewModel.state.value.error)
    }

    @Test
    fun `saving before start does nothing`() = runTest {
        viewModel.onMealTypeChange("lunch")

        viewModel.save()

        assertTrue(repository.added.isEmpty())
    }

    @Test
    fun `the add meal form cannot save while the recipe failed to load`() = runTest {
        repository.recipeFailure = ApiException.NetworkError()
        viewModel.start("p1", "r1", mealType = "dinner")

        viewModel.save()

        assertTrue(repository.added.isEmpty(), "nothing is added while the recipe could not be loaded")
        assertEquals(AddMealError.NETWORK, viewModel.state.value.error)
    }

    // --- AIA-604: a meal type known in advance ---

    @Test
    fun `a meal type given at start is already chosen`() = runTest {
        viewModel.start("p1", "r1", mealType = "DINNER")

        assertEquals("dinner", viewModel.state.value.mealType)
    }

    @Test
    fun `an unknown meal type given at start is ignored`() = runTest {
        viewModel.start("p1", "r1", mealType = "brunch")

        assertNull(viewModel.state.value.mealType)
    }

    @Test
    fun `a retry keeps the meal type the user chose`() = runTest {
        repository.recipeFailure = ApiException.NetworkError()
        viewModel.start("p1", "r1", mealType = "dinner")
        viewModel.onMealTypeChange("lunch")

        repository.recipeFailure = null
        viewModel.start("p1", "r1", mealType = "dinner")

        assertEquals("lunch", viewModel.state.value.mealType)
    }

    @Test
    fun `a meal type given at start is the one added`() = runTest {
        viewModel.start("p1", "r1", mealType = "snack")

        viewModel.save()

        assertEquals("snack", repository.added.single().second.mealType)
    }
}
