package com.nutriplan.android.plans

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.a11y.hasLiveRegion
import com.nutriplan.android.screen.plans.MealPlanDetailScreenContent
import com.nutriplan.android.screen.plans.MealPlanDetailTestTags
import com.nutriplan.android.screen.plans.NutritionSummaryTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.NutrientProgress
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.NutritionalProgress
import com.nutriplan.shared.data.model.NutritionalSummary
import com.nutriplan.shared.data.model.NutritionalTargets
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.PlanMealRecipe
import com.nutriplan.shared.planning.MealPlanDetailError
import com.nutriplan.shared.planning.MealPlanDetailUiState
import com.nutriplan.shared.planning.groupMealsByDay
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * DPL-505: the plan detail renders meals by day and meal type, with nutrition per meal, and exposes
 * the add-meal entry point accessibly. Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
// A tall viewport so every lazily composed list item is on screen.
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2000dp", application = TestApplication::class)
class MealPlanDetailScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private fun meal(
        id: String,
        dayIndex: Int?,
        type: String,
        calories: Int? = null,
        servings: Double = 1.0,
        recipe: PlanMealRecipe? = null,
        macros: Boolean = false,
    ) = PlanMeal(
        id = id,
        mealType = type,
        servings = servings,
        dayIndex = dayIndex,
        recipe = recipe,
        nutritionalInfo = if (calories != null || macros) {
            NutritionalInfo(
                calories = calories,
                protein = if (macros) 20.5 else null,
                carbs = if (macros) 30.0 else null,
                fat = if (macros) 10.0 else null,
            )
        } else {
            null
        },
    )

    private fun plan(vararg meals: PlanMeal, summary: NutritionalSummary? = null) = MealPlan(
        id = "p1",
        name = "Week 40",
        startDate = "2026-10-01",
        endDate = "2026-10-07",
        dailyCalorieTarget = 2000,
        status = "active",
        meals = meals.toList(),
        nutritionalSummary = summary,
    )

    private fun loaded(plan: MealPlan, error: MealPlanDetailError? = null) = MealPlanDetailUiState(
        plan = plan,
        days = groupMealsByDay(plan.startDate, plan.meals),
        isLoading = false,
        error = error,
    )

    private fun render(
        state: MealPlanDetailUiState,
        onRetry: () -> Unit = {},
        onBack: () -> Unit = {},
        onAddMeal: () -> Unit = {},
        onEditMeal: (String) -> Unit = {},
    ) {
        compose.setContent {
            NutriPlanTheme {
                MealPlanDetailScreenContent(
                    state = state,
                    onRefresh = {},
                    onRetry = onRetry,
                    onBack = onBack,
                    onAddMeal = onAddMeal,
                    onEditMeal = onEditMeal,
                )
            }
        }
    }

    @Test
    fun `first load shows a labelled progress indicator`() {
        render(MealPlanDetailUiState())

        compose.onNodeWithTag(MealPlanDetailTestTags.LOADING).assertIsDisplayed()
        compose.onNodeWithContentDescription(str(R.string.cd_plan_detail_loading)).assertExists()
    }

    @Test
    fun `days are numbered and dated from the plan start, with meals under their meal type`() {
        render(
            loaded(
                plan(
                    meal("1", 0, "breakfast", calories = 300),
                    meal("2", 0, "lunch", calories = 600),
                    meal("3", 1, "dinner", calories = 700),
                ),
            ),
        )

        compose.onNodeWithText("Week 40").assertIsDisplayed()
        compose.onNodeWithText("Day 1 · Thursday, October 1, 2026").assertIsDisplayed()
        compose.onNodeWithText("Day 2 · Friday, October 2, 2026").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText(str(R.string.meal_type_breakfast)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.meal_type_lunch)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.meal_type_dinner)).assertIsDisplayed()
        assertEquals(3, compose.onAllNodesWithTag(MealPlanDetailTestTags.MEAL_CARD).fetchSemanticsNodes().size)
    }

    @Test
    fun `meal cards show servings, calories and macros, and the day shows its total`() {
        render(
            loaded(
                plan(
                    meal("1", 0, "breakfast", calories = 300, servings = 1.5, macros = true),
                    meal("2", 0, "lunch", calories = 600),
                ),
            ),
        )

        compose.onNodeWithText(str(R.string.plan_detail_day_calories, 900)).assertIsDisplayed()
        compose.onNodeWithText("Servings: 1.5 · 300 kcal").assertIsDisplayed()
        compose.onNodeWithText("Protein 20.5 g · Carbs 30 g · Fat 10 g").assertIsDisplayed()
        compose.onNodeWithText("Servings: 1 · 600 kcal").assertIsDisplayed()
    }

    @Test
    fun `a meal shows its recipe name when the server included it, otherwise a neutral title`() {
        render(
            loaded(
                plan(
                    meal("1", 0, "lunch", recipe = PlanMealRecipe("r1", "Lentil soup")),
                    meal("2", 0, "dinner"),
                ),
            ),
        )

        compose.onNodeWithText("Lentil soup").assertIsDisplayed()
        assertEquals(1, compose.onAllNodesWithText(str(R.string.plan_detail_meal_unnamed)).fetchSemanticsNodes().size)
    }

    @Test
    fun `a meal without nutrition data still shows its servings`() {
        render(loaded(plan(meal("1", 0, "lunch", servings = 2.0))))

        compose.onNodeWithText("Servings: 2").assertIsDisplayed()
    }

    @Test
    fun `meals not assigned to a day are grouped under their own heading`() {
        render(loaded(plan(meal("1", null, "snack", calories = 120))))

        compose.onNodeWithText(str(R.string.plan_detail_day_unassigned)).assertIsDisplayed()
    }

    @Test
    fun `an unknown meal type is shown as sent`() {
        render(loaded(plan(meal("1", 0, "brunch"))))

        compose.onNodeWithText("brunch").assertIsDisplayed()
    }

    @Test
    fun `the summary shows the target and, when known, the daily average against it`() {
        val summary = NutritionalSummary(
            dailyAverage = NutritionalInfo(calories = 128),
            targets = NutritionalTargets(calories = 2000),
            progress = NutritionalProgress(calories = NutrientProgress(target = 2000.0, actual = 128.0, percentOfTarget = 6.4)),
        )
        render(loaded(plan(meal("1", 0, "lunch"), summary = summary)))

        compose.onNodeWithText(str(R.string.plan_detail_target_calories, 2000)).assertIsDisplayed()
        // The daily average against the target is drawn by the nutrition card (DPL-605).
        compose.onNodeWithTag(NutritionSummaryTestTags.CARD).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.nutrition_kcal_of_target, "128", "2,000")).assertIsDisplayed()
    }

    @Test
    fun `a plan without nutrition data shows no nutrition card`() {
        render(loaded(plan(meal("1", 0, "lunch"))))

        compose.onNodeWithTag(NutritionSummaryTestTags.CARD).assertDoesNotExist()
    }

    @Test
    fun `each day header and the title are headings for screen readers`() {
        render(loaded(plan(meal("1", 0, "lunch", calories = 500))))

        compose.onNodeWithText("Day 1 · Thursday, October 1, 2026").assert(isHeading())
        compose.onNodeWithText("Week 40").assert(isHeading())
    }

    @Test
    fun `add meal is available, and there is no edit action the API cannot serve`() {
        var added = 0
        render(loaded(plan(meal("1", 0, "lunch"))), onAddMeal = { added++ })

        compose.onNodeWithTag(MealPlanDetailTestTags.ADD_MEAL).performScrollTo().performClick()
        assertEquals(1, added)
        compose.onNodeWithContentDescription("Edit plan").assertDoesNotExist()
    }

    @Test
    fun `a plan without meals offers to add the first one`() {
        var added = 0
        render(loaded(plan()), onAddMeal = { added++ })

        compose.onNodeWithText(str(R.string.plan_detail_empty_title)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.plan_detail_add_meal)).performClick()
        assertEquals(1, added)
    }

    @Test
    fun `failing with nothing saved shows the error with retry`() {
        var retried = 0
        render(
            MealPlanDetailUiState(isLoading = false, error = MealPlanDetailError.NETWORK),
            onRetry = { retried++ },
        )

        compose.onNodeWithText(str(R.string.error_plan_detail_network)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.meal_plans_retry)).performClick()
        assertEquals(1, retried)
    }

    @Test
    fun `a deleted plan explains it and goes back instead of retrying`() {
        var backed = 0
        var retried = 0
        render(
            MealPlanDetailUiState(isLoading = false, error = MealPlanDetailError.NOT_FOUND),
            onRetry = { retried++ },
            onBack = { backed++ },
        )

        compose.onNodeWithText(str(R.string.error_plan_detail_not_found)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.plan_detail_back_to_plans)).performClick()
        assertEquals(1, backed)
        assertEquals(0, retried)
    }

    @Test
    fun `failing with a saved plan keeps it and announces the problem politely`() {
        render(loaded(plan(meal("1", 0, "lunch", calories = 500)), error = MealPlanDetailError.NETWORK))

        compose.onNodeWithText("Week 40").assertIsDisplayed()
        compose.onNodeWithTag(MealPlanDetailTestTags.ERROR_BANNER).assert(hasLiveRegion())
        compose.onNodeWithText(str(R.string.error_plan_detail_network_saved)).assertIsDisplayed()
    }

    @Test
    fun `the back button works`() {
        var backed = 0
        render(loaded(plan(meal("1", 0, "lunch"))), onBack = { backed++ })

        compose.onNodeWithContentDescription(str(R.string.cd_meal_plans_back)).performClick()
        assertEquals(1, backed)
    }

    @Test
    fun `tapping a meal opens it for editing`() {
        var edited: String? = null
        render(loaded(plan(meal("m7", 0, "lunch", calories = 600))), onEditMeal = { edited = it })

        compose.onNodeWithTag(MealPlanDetailTestTags.MEAL_CARD).performClick()

        assertEquals("m7", edited)
    }

    @Test
    fun `a rated meal shows its rating and an unrated one does not`() {
        val rated = PlanMeal(id = "m1", mealType = "lunch", servings = 1.0, dayIndex = 0, satisfactionLevel = 4)
        render(loaded(plan(rated, meal("m2", 0, "dinner"))))

        compose.onNodeWithText(str(R.string.plan_detail_meal_rated, 4)).assertIsDisplayed()
        assertEquals(
            1,
            compose.onAllNodesWithText(str(R.string.plan_detail_meal_rated, 4)).fetchSemanticsNodes().size,
        )
    }
}