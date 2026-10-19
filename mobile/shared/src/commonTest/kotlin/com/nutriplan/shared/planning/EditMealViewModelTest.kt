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
import kotlin.test.assertNull
import kotlin.test.assertTrue

class EditMealViewModelTest {

    private class FakeDietary : DietaryRepository {
        var meals: List<PlanMeal> = listOf(
            PlanMeal(id = "m1", mealType = "lunch", servings = 2.0, dayIndex = 1, satisfactionLevel = null),
            PlanMeal(id = "m2", mealType = "dinner", servings = 1.5, dayIndex = null, satisfactionLevel = 3),
        )
        var planFailure: Throwable? = null
        var updateFailure: Throwable? = null
        var removeFailure: Throwable? = null
        var gate: CompletableDeferred<Unit>? = null
        val updates = mutableListOf<Triple<String, String, UpdateMealRequest>>()
        val removals = mutableListOf<Pair<String, String>>()
        var planCalls = 0

        override suspend fun getMealPlan(planId: String): MealPlan {
            planCalls++
            planFailure?.let { throw it }
            return MealPlan(
                id = planId,
                name = "Week",
                startDate = "2026-10-01",
                endDate = "2026-10-03",
                dailyCalorieTarget = 2000,
                status = "draft",
                meals = meals,
            )
        }

        override suspend fun updateMeal(planId: String, mealId: String, request: UpdateMealRequest): PlanMeal {
            updates += Triple(planId, mealId, request)
            gate?.await()
            updateFailure?.let { throw it }
            return meals.first { it.id == mealId }
        }

        override suspend fun removeMeal(planId: String, mealId: String) {
            removals += planId to mealId
            gate?.await()
            removeFailure?.let { throw it }
        }

        override suspend fun addMeal(planId: String, request: AddMealRequest): PlanMeal = error("unused")
        override suspend fun searchRecipes(query: RecipeSearchQuery): List<Recipe> = error("unused")
        override suspend fun getRecipe(recipeId: String): Recipe = error("unused")
        override suspend fun getNutritionDisclaimer(): NutritionDisclaimer = error("unused")
        override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlanSummary> = error("unused")
        override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan = error("unused")
        override suspend fun updateMealPlanStatus(planId: String, status: String): MealPlan = error("unused")
    }

    private val repository = FakeDietary()
    private val viewModel = EditMealViewModel(repository)

    // --- loading ---

    @Test
    fun `starts in the loading state`() {
        assertTrue(viewModel.state.value.isLoading)
        assertNull(viewModel.state.value.meal)
    }

    @Test
    fun `start fills the form from the meal and lists the plan's days`() = runTest {
        viewModel.start("p1", "m1")

        val state = viewModel.state.value
        assertEquals("m1", state.meal?.id)
        assertEquals("2", state.servings)
        assertEquals(1, state.dayIndex)
        assertNull(state.satisfaction)
        assertEquals(3, state.days.size)
        assertFalse(state.isLoading)
        assertFalse(state.hasChanges)
    }

    @Test
    fun `fractional servings keep their decimals`() = runTest {
        viewModel.start("p1", "m2")

        assertEquals("1.5", viewModel.state.value.servings)
        assertEquals(3, viewModel.state.value.satisfaction)
    }

    @Test
    fun `a meal that is not in the plan is not found`() = runTest {
        viewModel.start("p1", "nope")

        assertEquals(EditMealError.NOT_FOUND, viewModel.state.value.loadError)
        assertNull(viewModel.state.value.meal)
    }

    @Test
    fun `a failed load is reported and can be retried`() = runTest {
        repository.planFailure = ApiException.NetworkError()
        viewModel.start("p1", "m1")
        assertEquals(EditMealError.NETWORK, viewModel.state.value.loadError)

        repository.planFailure = null
        viewModel.start("p1", "m1")

        assertNull(viewModel.state.value.loadError)
        assertEquals("m1", viewModel.state.value.meal?.id)
    }

    @Test
    fun `a retry keeps what the user already edited`() = runTest {
        viewModel.start("p1", "m1")
        viewModel.onServingsChange("4")

        viewModel.start("p1", "m1")

        assertEquals("4", viewModel.state.value.servings)
    }

    // --- fields ---

    @Test
    fun `changes are detected against the saved meal`() = runTest {
        viewModel.start("p1", "m1")

        viewModel.onServingsChange("3")
        assertTrue(viewModel.state.value.hasChanges)
        viewModel.onServingsChange("2")
        assertFalse(viewModel.state.value.hasChanges)

        viewModel.onSatisfactionChange(5)
        assertTrue(viewModel.state.value.hasChanges)
    }

    @Test
    fun `only ratings from 1 to 5 are accepted`() = runTest {
        viewModel.start("p1", "m1")

        viewModel.onSatisfactionChange(0)
        viewModel.onSatisfactionChange(6)
        assertNull(viewModel.state.value.satisfaction)

        viewModel.onSatisfactionChange(4)
        assertEquals(4, viewModel.state.value.satisfaction)
    }

    @Test
    fun `a day can be changed but not taken away once set`() = runTest {
        viewModel.start("p1", "m1")

        viewModel.onDayChange(2)
        assertEquals(2, viewModel.state.value.dayIndex)

        viewModel.onDayChange(null)
        assertEquals(2, viewModel.state.value.dayIndex)
        assertFalse(viewModel.state.value.canClearDay)

        viewModel.onDayChange(9)
        assertEquals(2, viewModel.state.value.dayIndex, "a day outside the plan is ignored")
    }

    @Test
    fun `a meal without a day can have one chosen and cleared again`() = runTest {
        viewModel.start("p1", "m2")
        assertTrue(viewModel.state.value.canClearDay)

        viewModel.onDayChange(0)
        assertEquals(0, viewModel.state.value.dayIndex)
        viewModel.onDayChange(null)
        assertNull(viewModel.state.value.dayIndex)
    }

    // --- saving ---

    @Test
    fun `save sends only the fields that changed`() = runTest {
        viewModel.start("p1", "m1")
        viewModel.onServingsChange("3")
        viewModel.onSatisfactionChange(4)

        viewModel.save()

        assertEquals(
            listOf(Triple("p1", "m1", UpdateMealRequest(servings = 3.0, satisfactionLevel = 4))),
            repository.updates,
        )
        assertTrue(viewModel.state.value.isDone)
    }

    @Test
    fun `changing only the day sends only the day`() = runTest {
        viewModel.start("p1", "m1")
        viewModel.onDayChange(0)

        viewModel.save()

        assertEquals(UpdateMealRequest(dayIndex = 0), repository.updates.single().third)
    }

    @Test
    fun `saving without changes sends nothing and finishes`() = runTest {
        viewModel.start("p1", "m1")

        viewModel.save()

        assertTrue(repository.updates.isEmpty())
        assertTrue(viewModel.state.value.isDone)
    }

    @Test
    fun `servings must be a positive number`() = runTest {
        viewModel.start("p1", "m1")

        suspend fun check(text: String, expected: EditMealFieldError) {
            viewModel.onServingsChange(text)
            viewModel.save()
            assertEquals(expected, viewModel.state.value.servingsError, "servings '$text'")
        }
        check("", EditMealFieldError.SERVINGS_REQUIRED)
        check("0", EditMealFieldError.SERVINGS_INVALID)
        check("100", EditMealFieldError.SERVINGS_INVALID)
        assertTrue(repository.updates.isEmpty())
    }

    @Test
    fun `a failed save keeps the form and can be retried`() = runTest {
        viewModel.start("p1", "m1")
        viewModel.onSatisfactionChange(2)
        repository.updateFailure = ApiException.NetworkError()

        viewModel.save()
        assertEquals(EditMealError.NETWORK, viewModel.state.value.error)
        assertFalse(viewModel.state.value.isDone)
        assertEquals(2, viewModel.state.value.satisfaction)

        repository.updateFailure = null
        viewModel.save()

        assertTrue(viewModel.state.value.isDone)
        assertNull(viewModel.state.value.error)
    }

    @Test
    fun `failures map to stable codes`() = runTest {
        suspend fun errorFor(failure: Throwable): EditMealError? {
            val fake = FakeDietary().apply { updateFailure = failure }
            val vm = EditMealViewModel(fake)
            vm.start("p1", "m1")
            vm.onSatisfactionChange(5)
            vm.save()
            return vm.state.value.error
        }

        assertEquals(EditMealError.SESSION_EXPIRED, errorFor(ApiException.HttpError(401, null)))
        assertEquals(EditMealError.NOT_FOUND, errorFor(ApiException.HttpError(404, null)))
        assertEquals(EditMealError.REJECTED, errorFor(ApiException.HttpError(422, null)))
        assertEquals(EditMealError.SERVER_PROBLEM, errorFor(ApiException.HttpError(500, null)))
        assertEquals(EditMealError.UNKNOWN, errorFor(ApiException.HttpError(418, null)))
    }

    @Test
    fun `a second save while one is running is ignored`() = runTest {
        viewModel.start("p1", "m1")
        viewModel.onSatisfactionChange(3)
        val gate = CompletableDeferred<Unit>()
        repository.gate = gate

        val first = launch { viewModel.save() }
        testScheduler.advanceUntilIdle()
        assertTrue(viewModel.state.value.isSaving)
        viewModel.save()
        gate.complete(Unit)
        first.join()

        assertEquals(1, repository.updates.size)
    }

    @Test
    fun `cancelling a save rethrows and clears the saving flag`() = runTest {
        viewModel.start("p1", "m1")
        viewModel.onSatisfactionChange(3)
        repository.gate = CompletableDeferred()

        val job = launch { viewModel.save() }
        testScheduler.advanceUntilIdle()
        job.cancel()
        job.join()

        assertFalse(viewModel.state.value.isSaving)
        assertNull(viewModel.state.value.error)
    }

    // --- removing ---

    @Test
    fun `remove deletes the meal and finishes`() = runTest {
        viewModel.start("p1", "m1")

        viewModel.remove()

        assertEquals(listOf("p1" to "m1"), repository.removals)
        assertTrue(viewModel.state.value.isDone)
        assertFalse(viewModel.state.value.isRemoving)
    }

    @Test
    fun `a failed removal is reported and can be retried`() = runTest {
        viewModel.start("p1", "m1")
        repository.removeFailure = ApiException.NetworkError()

        viewModel.remove()
        assertEquals(EditMealError.NETWORK, viewModel.state.value.error)
        assertFalse(viewModel.state.value.isDone)

        repository.removeFailure = null
        viewModel.remove()

        assertTrue(viewModel.state.value.isDone)
    }

    @Test
    fun `removing a meal that is already gone counts as removed`() = runTest {
        viewModel.start("p1", "m1")
        repository.removeFailure = ApiException.HttpError(404, null)

        viewModel.remove()

        assertTrue(viewModel.state.value.isDone)
        assertNull(viewModel.state.value.error)
    }

    @Test
    fun `nothing happens before the meal is loaded or after it is done`() = runTest {
        viewModel.save()
        viewModel.remove()
        assertTrue(repository.updates.isEmpty() && repository.removals.isEmpty())

        viewModel.start("p1", "m1")
        viewModel.remove()
        viewModel.remove()
        viewModel.save()

        assertEquals(1, repository.removals.size)
        assertTrue(repository.updates.isEmpty())
    }
}
