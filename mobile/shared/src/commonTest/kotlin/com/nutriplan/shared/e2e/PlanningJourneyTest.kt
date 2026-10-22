package com.nutriplan.shared.e2e

import com.nutriplan.shared.data.model.DietaryMacroTargets
import com.nutriplan.shared.data.model.DietaryPreferences
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.DietaryRepositoryImpl
import com.nutriplan.shared.planning.AddMealViewModel
import com.nutriplan.shared.planning.MealPlanDetailViewModel
import com.nutriplan.shared.planning.MealPlanFormViewModel
import com.nutriplan.shared.planning.Nutrient
import com.nutriplan.shared.planning.ProgressStatus
import com.nutriplan.shared.planning.toNutritionSummaryUi
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * DPL-704: the planning journey through the shared layer (create a plan, add meals, see the
 * nutrition), on every platform the shared code runs on: this runs on the JVM in the Android jobs
 * and on the iOS simulator in the iOS job, through the same view-models the Compose and SwiftUI
 * screens use, against a stateful Dietary backend stand-in. The Android UI version of the journey is
 * `PlanningJourneyE2ETest` in the app module.
 */
class PlanningJourneyTest {

    private val backend = FakeDietaryBackend(
        listOf(
            FakeDietaryBackend.CatalogRecipe("oats", "Overnight Oats", calories = 350, protein = 12.0, carbs = 60.0, fat = 8.0, sugar = 10.0),
            FakeDietaryBackend.CatalogRecipe("salad", "Chicken Salad", calories = 280, protein = 18.0, carbs = 10.0, fat = 15.0, sugar = 4.0),
        ),
    )
    private lateinit var repository: DietaryRepositoryImpl

    /** The signed-in user's saved preferences: the form prefills the target from them. */
    private val preferences = DietaryPreferences(
        dailyCalorieTarget = 2000,
        macroTargets = DietaryMacroTargets(proteinGrams = 150),
    )

    @BeforeTest
    fun setUp() {
        HttpClientProvider.create(backend.engine, authRepository = null)
        repository = DietaryRepositoryImpl()
    }

    @AfterTest
    fun tearDown() = HttpClientProvider.reset()

    /** Create a one-week plan (2026-10-01 to 2026-10-07) through the form and return its id. */
    private suspend fun createPlan(): String {
        val form = MealPlanFormViewModel(repository) { preferences }
        form.start(today = "2026-10-01")
        assertEquals("2000", form.state.value.calories, "the target is prefilled from the preferences")
        form.onNameChange("Week 40")

        assertTrue(form.save(), "the plan should be created: ${form.state.value}")
        return assertNotNull(form.state.value.createdPlanId)
    }

    private suspend fun addMeal(planId: String, recipeId: String, mealType: String, servings: String, day: Int) {
        val form = AddMealViewModel(repository)
        form.start(planId, recipeId)
        form.onMealTypeChange(mealType)
        form.onServingsChange(servings)
        form.onDayChange(day)

        form.save()

        assertTrue(form.state.value.isDone, "the meal should be added: ${form.state.value}")
    }

    @Test
    fun create_a_plan_add_meals_and_see_the_nutrition_summary() = runTest {
        val planId = createPlan()
        addMeal(planId, "oats", mealType = "breakfast", servings = "2", day = 0)
        addMeal(planId, "salad", mealType = "lunch", servings = "1", day = 1)

        val detail = MealPlanDetailViewModel(repository)
        detail.load(planId)

        val state = detail.state.value
        val plan = assertNotNull(state.plan)
        assertEquals("Week 40", plan.name)
        assertEquals(listOf("breakfast", "lunch"), plan.meals.map { it.mealType })
        assertEquals(listOf(0, 1), state.days.map { it.dayIndex }, "one meal on each of the first two days")

        // 2 x 350 + 280 = 980 kcal over 7 days = 140 a day, against a 2,000 kcal target.
        val summary = plan.nutritionalSummary.toNutritionSummaryUi()
        val calories = assertNotNull(summary.row(Nutrient.CALORIES))
        assertEquals(980.0, calories.total)
        assertEquals(140.0, calories.average)
        assertEquals(2000.0, calories.target)
        assertEquals(7.0, calories.percentOfTarget)
        assertEquals(ProgressStatus.UNDER, calories.status)

        // 2 x 12 + 18 = 42 g of protein = 6 g a day, against the 150 g target from the preferences.
        val protein = assertNotNull(summary.row(Nutrient.PROTEIN))
        assertEquals(6.0, protein.average)
        assertEquals(150.0, protein.target)
        assertEquals(ProgressStatus.UNDER, protein.status)

        // No carbs target was set: the average is shown, with no judgement.
        val carbs = assertNotNull(summary.row(Nutrient.CARBS))
        assertEquals(ProgressStatus.UNKNOWN, carbs.status)

        assertEquals(
            listOf(
                "POST /meal-plans",
                "GET /recipes/oats", "GET /meal-plans/$planId", "POST /meal-plans/$planId/meals",
                "PATCH /meal-plans/$planId/meals/meal-2",
                "GET /recipes/salad", "GET /meal-plans/$planId", "POST /meal-plans/$planId/meals",
                "PATCH /meal-plans/$planId/meals/meal-3",
                "GET /meal-plans/$planId",
            ),
            backend.requests,
        )
    }

    @Test
    fun meeting_the_calorie_target_exactly_is_on_target_and_going_past_it_is_over() = runTest {
        val planId = createPlan()
        // 40 x 350 = 14,000 kcal over 7 days = exactly 2,000 a day.
        addMeal(planId, "oats", mealType = "dinner", servings = "40", day = 2)

        val detail = MealPlanDetailViewModel(repository)
        detail.load(planId)
        val onTarget = detail.state.value.plan!!.nutritionalSummary.toNutritionSummaryUi().row(Nutrient.CALORIES)!!
        assertEquals(ProgressStatus.ON_TARGET, onTarget.status)

        // One more snack of 280 kcal tips it over: 14,280 / 7 = 2,040 a day.
        addMeal(planId, "salad", mealType = "snack", servings = "1", day = 3)
        detail.refresh()
        val over = detail.state.value.plan!!.nutritionalSummary.toNutritionSummaryUi().row(Nutrient.CALORIES)!!
        assertEquals(ProgressStatus.OVER, over.status)
        assertEquals(2040.0, over.average)
        assertEquals(40.0, over.overBy)
    }

    @Test
    fun a_new_plan_has_no_nutrition_to_show_until_meals_are_added() = runTest {
        val planId = createPlan()

        val detail = MealPlanDetailViewModel(repository)
        detail.load(planId)

        assertTrue(detail.state.value.hasNoMeals)
        val calories = detail.state.value.plan!!.nutritionalSummary.toNutritionSummaryUi().row(Nutrient.CALORIES)!!
        assertEquals(0.0, calories.average)
        assertEquals(ProgressStatus.UNDER, calories.status)
    }
}
