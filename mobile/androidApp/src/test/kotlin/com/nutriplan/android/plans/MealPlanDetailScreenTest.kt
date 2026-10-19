package com.nutriplan.android.plans

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
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
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.PlanMeal
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
 * the add/edit entry points accessibly. Runs on the JVM via Robolectric.
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
        date: String,
        type: String,
        calories: Int? = null,
        portion: Double? = null,
    ) = PlanMeal(
        id = id,
        planId = "p1",
        recipeId = "r-$id",
        recipeName = "Recipe $id",
        mealType = type,
        scheduledDate = date,
        calories = calories,
        portionSize = portion,
    )

    private fun loaded(
        vararg meals: PlanMeal,
        error: MealPlanDetailError? = null,
    ): MealPlanDetailUiState {
        val plan = MealPlan(
            id = "p1",
            name = "Week 40",
            userId = "user-1",
            startDate = "2026-10-01",
            endDate = "2026-10-07",
            targetCalories = 2000,
            meals = meals.toList(),
            status = "ACTIVE",
        )
        return MealPlanDetailUiState(
            plan = plan,
            days = groupMealsByDay(meals.toList()),
            isLoading = false,
            error = error,
        )
    }

    private fun render(
        state: MealPlanDetailUiState,
        onRetry: () -> Unit = {},
        onBack: () -> Unit = {},
        onAddMeal: () -> Unit = {},
        onEditPlan: () -> Unit = {},
    ) {
        compose.setContent {
            NutriPlanTheme {
                MealPlanDetailScreenContent(
                    state = state,
                    onRefresh = {},
                    onRetry = onRetry,
                    onBack = onBack,
                    onAddMeal = onAddMeal,
                    onEditPlan = onEditPlan,
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
    fun `meals are shown under their day and meal type`() {
        render(
            loaded(
                meal("1", "2026-10-01", "BREAKFAST", calories = 300, portion = 1.0),
                meal("2", "2026-10-01", "LUNCH", calories = 600, portion = 1.5),
                meal("3", "2026-10-02", "DINNER", calories = 700),
            ),
        )

        compose.onNodeWithText("Week 40").assertIsDisplayed()
        compose.onNodeWithText("Thursday, October 1, 2026").assertIsDisplayed()
        compose.onNodeWithText(str(R.string.meal_type_breakfast)).assertIsDisplayed()
        compose.onNodeWithText("Recipe 1").assertIsDisplayed()
        compose.onNodeWithText("Recipe 2").assertIsDisplayed()
        compose.onNodeWithText("Friday, October 2, 2026").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("Recipe 3").performScrollTo().assertIsDisplayed()
    }

    @Test
    fun `meal cards show calories and portion, and the day shows its total`() {
        render(
            loaded(
                meal("1", "2026-10-01", "BREAKFAST", calories = 300, portion = 1.0),
                meal("2", "2026-10-01", "LUNCH", calories = 600, portion = 1.5),
            ),
        )

        compose.onNodeWithText(str(R.string.plan_detail_day_calories, 900)).assertIsDisplayed()
        compose.onNodeWithText("300 kcal · Portion: 1").assertIsDisplayed()
        compose.onNodeWithText("600 kcal · Portion: 1.5").assertIsDisplayed()
    }

    @Test
    fun `a meal without nutrition data just shows the recipe`() {
        render(loaded(meal("1", "2026-10-01", "LUNCH")))

        compose.onNodeWithText("Recipe 1").assertIsDisplayed()
        assertEquals(1, compose.onAllNodesWithTag(MealPlanDetailTestTags.MEAL_CARD).fetchSemanticsNodes().size)
    }

    @Test
    fun `an unknown meal type is shown as sent`() {
        render(loaded(meal("1", "2026-10-01", "BRUNCH")))

        compose.onNodeWithText("BRUNCH").assertIsDisplayed()
    }

    @Test
    fun `each day header is a heading for screen readers`() {
        render(loaded(meal("1", "2026-10-01", "LUNCH", calories = 500)))

        compose.onNodeWithText("Thursday, October 1, 2026").assert(isHeading())
        compose.onNodeWithText("Week 40").assert(isHeading())
    }

    @Test
    fun `add meal and edit plan are available`() {
        var added = 0
        var edited = 0
        render(
            loaded(meal("1", "2026-10-01", "LUNCH")),
            onAddMeal = { added++ },
            onEditPlan = { edited++ },
        )

        compose.onNodeWithTag(MealPlanDetailTestTags.ADD_MEAL).performScrollTo().performClick()
        compose.onNodeWithTag(MealPlanDetailTestTags.EDIT).performClick()
        compose.onNodeWithContentDescription(str(R.string.cd_plan_detail_edit)).assertExists()

        assertEquals(1, added)
        assertEquals(1, edited)
    }

    @Test
    fun `a plan without meals offers to add the first one`() {
        var added = 0
        render(loaded(), onAddMeal = { added++ })

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
        render(loaded(meal("1", "2026-10-01", "LUNCH"), error = MealPlanDetailError.NETWORK))

        compose.onNodeWithText("Recipe 1").assertIsDisplayed()
        compose.onNodeWithTag(MealPlanDetailTestTags.ERROR_BANNER).assert(hasLiveRegion())
        compose.onNodeWithText(str(R.string.error_plan_detail_network_saved)).assertIsDisplayed()
    }

    @Test
    fun `the back button works`() {
        var backed = 0
        render(loaded(meal("1", "2026-10-01", "LUNCH")), onBack = { backed++ })

        compose.onNodeWithContentDescription(str(R.string.cd_meal_plans_back)).performClick()
        assertEquals(1, backed)
    }
}
