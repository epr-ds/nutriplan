package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.UpdateMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.DietaryMacroTargets
import com.nutriplan.shared.data.model.DietaryPreferences
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

class MealPlanFormViewModelTest {

    private class FakeDietary : DietaryRepository {
        val created = mutableListOf<CreateMealPlanRequest>()
        var failure: Throwable? = null
        var gate: CompletableDeferred<Unit>? = null

        override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan {
            created += request
            gate?.await()
            failure?.let { throw it }
            return MealPlan(
                id = "new-plan",
                name = request.name,
                startDate = request.startDate,
                endDate = request.endDate,
                dailyCalorieTarget = request.dailyCalorieTarget,
                status = "draft",
            )
        }

        override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlanSummary> = error("unused")
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
    private var preferences: DietaryPreferences? = null
    private val viewModel = MealPlanFormViewModel(repository) { preferences }

    private val today = "2026-10-01"

    /** A form that passes every check. */
    private fun fillValid() {
        viewModel.start(today)
        viewModel.onNameChange("Week 40")
        viewModel.onCaloriesChange("2000")
    }

    // --- defaults and prefill ---

    @Test
    fun `starts with a week from today`() {
        viewModel.start(today)

        val state = viewModel.state.value
        assertEquals("2026-10-01", state.startDate)
        assertEquals("2026-10-07", state.endDate)
        assertEquals("", state.name)
    }

    @Test
    fun `the calorie target is prefilled from the dietary preferences`() {
        preferences = DietaryPreferences(dailyCalorieTarget = 2200)

        viewModel.start(today)

        assertEquals("2200", viewModel.state.value.calories)
        assertTrue(viewModel.state.value.caloriesPrefilled)
    }

    @Test
    fun `without preferences the calories start empty and are not marked prefilled`() {
        viewModel.start(today)

        assertEquals("", viewModel.state.value.calories)
        assertFalse(viewModel.state.value.caloriesPrefilled)
    }

    @Test
    fun `a useless saved target is not prefilled`() {
        preferences = DietaryPreferences(dailyCalorieTarget = 0)

        viewModel.start(today)

        assertEquals("", viewModel.state.value.calories)
    }

    @Test
    fun `editing the calories drops the prefilled note`() {
        preferences = DietaryPreferences(dailyCalorieTarget = 2200)
        viewModel.start(today)

        viewModel.onCaloriesChange("2100")

        assertFalse(viewModel.state.value.caloriesPrefilled)
    }

    // --- editing ---

    @Test
    fun `calories keep only digits and a sensible length`() {
        viewModel.onCaloriesChange("2,0a0 0kcal")
        assertEquals("2000", viewModel.state.value.calories)

        viewModel.onCaloriesChange("123456789")
        assertEquals("123456", viewModel.state.value.calories)
    }

    @Test
    fun `moving the start past the end moves the end along, keeping the length`() {
        viewModel.start("2026-10-01") // Oct 1 to Oct 7: a 6 day span

        viewModel.onStartDateChange("2026-10-20")

        assertEquals("2026-10-20", viewModel.state.value.startDate)
        assertEquals("2026-10-26", viewModel.state.value.endDate)
    }

    @Test
    fun `moving the start earlier leaves the end alone`() {
        viewModel.start("2026-10-10")

        viewModel.onStartDateChange("2026-10-05")

        assertEquals("2026-10-16", viewModel.state.value.endDate)
    }

    @Test
    fun `editing a field clears its error and any form error`() = runTest {
        viewModel.start(today)
        viewModel.save()
        assertEquals(PlanFieldError.NAME_REQUIRED, viewModel.state.value.nameError)

        viewModel.onNameChange("W")

        assertNull(viewModel.state.value.nameError)
    }

    // --- validation ---

    @Test
    fun `an empty form lists what is missing`() {
        viewModel.start(today)

        assertFalse(viewModel.validate())

        val state = viewModel.state.value
        assertEquals(PlanFieldError.NAME_REQUIRED, state.nameError)
        assertEquals(PlanFieldError.CALORIES_REQUIRED, state.caloriesError)
        assertNull(state.startDateError)
        assertNull(state.endDateError)
    }

    @Test
    fun `a blank name is not a name`() {
        fillValid()
        viewModel.onNameChange("   ")

        assertFalse(viewModel.validate())
        assertEquals(PlanFieldError.NAME_REQUIRED, viewModel.state.value.nameError)
    }

    @Test
    fun `the end date may not be before the start date`() {
        fillValid()
        viewModel.onEndDateChange("2026-09-30")

        assertFalse(viewModel.validate())
        assertEquals(PlanFieldError.END_BEFORE_START, viewModel.state.value.endDateError)
    }

    @Test
    fun `a one day plan is valid`() {
        fillValid()
        viewModel.onEndDateChange(today)

        assertTrue(viewModel.validate())
    }

    @Test
    fun `missing or impossible dates are reported`() {
        fillValid()
        viewModel.onStartDateChange("")
        viewModel.onEndDateChange("2026-02-30")

        assertFalse(viewModel.validate())

        assertEquals(PlanFieldError.START_DATE_REQUIRED, viewModel.state.value.startDateError)
        assertEquals(PlanFieldError.END_DATE_REQUIRED, viewModel.state.value.endDateError)
    }

    @Test
    fun `zero calories are not a target`() {
        fillValid()
        viewModel.onCaloriesChange("0")

        assertFalse(viewModel.validate())
        assertEquals(PlanFieldError.CALORIES_INVALID, viewModel.state.value.caloriesError)
    }

    // --- saving ---

    @Test
    fun `saving sends the contract request with trimmed name and the preferences extras`() = runTest {
        preferences = DietaryPreferences(
            dietType = "Vegan",
            dailyCalorieTarget = 2200,
            macroTargets = DietaryMacroTargets(proteinGrams = 150),
        )
        viewModel.start(today)
        viewModel.onNameChange("  Week 40  ")

        assertTrue(viewModel.save())

        val request = repository.created.single()
        assertEquals("Week 40", request.name)
        assertEquals("2026-10-01", request.startDate)
        assertEquals("2026-10-07", request.endDate)
        assertEquals(2200, request.dailyCalorieTarget)
        assertEquals(150, request.macroTargets?.proteinGrams)
        assertEquals("vegan", request.dietaryType)
        assertEquals("new-plan", viewModel.state.value.createdPlanId)
        assertFalse(viewModel.state.value.isSaving)
    }

    @Test
    fun `a diet type the plan does not accept is left out`() = runTest {
        preferences = DietaryPreferences(dietType = "mediterranean", dailyCalorieTarget = 2000)
        viewModel.start(today)
        viewModel.onNameChange("Plan")

        viewModel.save()

        assertNull(repository.created.single().dietaryType)
    }

    @Test
    fun `an invalid form is not sent`() = runTest {
        viewModel.start(today)

        assertFalse(viewModel.save())

        assertTrue(repository.created.isEmpty())
        assertNull(viewModel.state.value.createdPlanId)
    }

    @Test
    fun `a second save while one is running does nothing`() = runTest {
        fillValid()
        repository.gate = CompletableDeferred()
        val first = launch { viewModel.save() }
        testScheduler.advanceUntilIdle()
        assertTrue(viewModel.state.value.isSaving)

        assertFalse(viewModel.save())
        assertEquals(1, repository.created.size)

        repository.gate!!.complete(Unit)
        first.join()
        assertEquals("new-plan", viewModel.state.value.createdPlanId)
    }

    @Test
    fun `failures map to localizable form errors and keep what was typed`() = runTest {
        suspend fun errorFor(failure: Throwable): MealPlanFormError? {
            val vm = MealPlanFormViewModel(FakeDietary().apply { this.failure = failure }) { null }
            vm.start(today)
            vm.onNameChange("Week 40")
            vm.onCaloriesChange("2000")
            vm.save()
            assertEquals("Week 40", vm.state.value.name)
            assertNull(vm.state.value.createdPlanId)
            return vm.state.value.error
        }

        assertEquals(MealPlanFormError.NETWORK, errorFor(ApiException.NetworkError()))
        assertEquals(MealPlanFormError.SERVER_PROBLEM, errorFor(ApiException.HttpError(503, null)))
        assertEquals(MealPlanFormError.SESSION_EXPIRED, errorFor(ApiException.HttpError(401, null)))
        assertEquals(
            MealPlanFormError.SESSION_EXPIRED,
            errorFor(ApiException.create("Unauthorized", ApiException.Code.UNAUTHORIZED)),
        )
        assertEquals(MealPlanFormError.REJECTED, errorFor(ApiException.HttpError(422, "{}")))
        assertEquals(MealPlanFormError.UNKNOWN, errorFor(IllegalStateException("boom")))
    }

    @Test
    fun `after a failure the same form can be saved again`() = runTest {
        fillValid()
        repository.failure = ApiException.NetworkError()
        assertFalse(viewModel.save())
        assertEquals(MealPlanFormError.NETWORK, viewModel.state.value.error)

        repository.failure = null
        assertTrue(viewModel.save())
        assertNull(viewModel.state.value.error)
    }

    @Test
    fun `cancelling a save clears the saving flag`() = runTest {
        fillValid()
        repository.gate = CompletableDeferred()
        val job = launch { viewModel.save() }
        testScheduler.advanceUntilIdle()
        assertTrue(viewModel.state.value.isSaving)

        job.cancel()
        job.join()

        assertFalse(viewModel.state.value.isSaving)
        assertNull(viewModel.state.value.error)
    }
}
