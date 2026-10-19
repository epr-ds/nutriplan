package com.nutriplan.android.plans

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.a11y.hasLiveRegion
import com.nutriplan.android.screen.plans.AddMealScreenContent
import com.nutriplan.android.screen.plans.AddMealTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.planning.AddMealDay
import com.nutriplan.shared.planning.AddMealError
import com.nutriplan.shared.planning.AddMealFieldError
import com.nutriplan.shared.planning.AddMealUiState
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * DPL-507: the add-meal form shows the recipe, asks for meal type, servings and (optionally) a day,
 * and every state (loading, errors, saving, day not set) is reachable and accessible. Runs on the
 * JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
// A tall viewport so the whole form is on screen.
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2000dp", application = TestApplication::class)
class AddMealScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private val recipe = Recipe(
        id = "r1",
        name = "Chicken bowl",
        nutritionalInfo = NutritionalInfo(calories = 520),
    )

    private val days = listOf(
        AddMealDay(0, "2026-10-01"),
        AddMealDay(1, "2026-10-02"),
        AddMealDay(2, "2026-10-03"),
    )

    private fun form(
        mealType: String? = null,
        servings: String = "1",
        dayIndex: Int? = null,
        days: List<AddMealDay> = this.days,
    ) = AddMealUiState(
        recipe = recipe,
        days = days,
        isLoading = false,
        mealType = mealType,
        servings = servings,
        dayIndex = dayIndex,
    )

    private class Calls {
        val mealTypes = mutableListOf<String>()
        val servings = mutableListOf<String>()
        val days = mutableListOf<Int?>()
        var submitted = 0
        var retriedLoad = 0
        var skipped = 0
        var backed = 0
    }

    private fun render(state: AddMealUiState): Calls {
        val calls = Calls()
        compose.setContent {
            NutriPlanTheme {
                AddMealScreenContent(
                    state = state,
                    onMealTypeChange = { calls.mealTypes += it },
                    onServingsChange = { calls.servings += it },
                    onDayChange = { calls.days += it },
                    onSubmit = { calls.submitted++ },
                    onRetryLoad = { calls.retriedLoad++ },
                    onSkipDay = { calls.skipped++ },
                    onBack = { calls.backed++ },
                )
            }
        }
        return calls
    }

    @Test
    fun `first load shows a labelled progress indicator`() {
        render(AddMealUiState())

        compose.onNodeWithTag(AddMealTestTags.LOADING).assertIsDisplayed()
        compose.onNodeWithContentDescription(str(R.string.cd_add_meal_loading)).assertExists()
    }

    @Test
    fun `the title is a heading and the recipe is shown`() {
        render(form())

        compose.onNode(isHeading() and hasText(str(R.string.add_meal_title))).assertIsDisplayed()
        compose.onNodeWithTag(AddMealTestTags.RECIPE).assertIsDisplayed()
        compose.onNodeWithText("Chicken bowl").assertIsDisplayed()
        compose.onNodeWithText(str(R.string.add_meal_recipe_calories, 520)).assertIsDisplayed()
    }

    @Test
    fun `all four meal types are offered and the chosen one is selected`() {
        render(form(mealType = "dinner"))

        assertEquals(4, compose.onAllNodesWithTag(AddMealTestTags.MEAL_TYPE_CHIP).fetchSemanticsNodes().size)
        compose.onNodeWithText(str(R.string.meal_type_dinner)).assertIsSelected()
    }

    @Test
    fun `choosing a meal type reports it`() {
        val calls = render(form())

        compose.onNodeWithText(str(R.string.meal_type_breakfast)).performClick()

        assertEquals(listOf("breakfast"), calls.mealTypes)
    }

    @Test
    fun `typing the servings reports the text`() {
        val calls = Calls()
        compose.setContent {
            // Hosted with real state, as in the app: a controlled field only shows what the state holds.
            var state by remember { mutableStateOf(form(servings = "")) }
            NutriPlanTheme {
                AddMealScreenContent(
                    state = state,
                    onMealTypeChange = {},
                    onServingsChange = { state = state.copy(servings = it); calls.servings += it },
                    onDayChange = {},
                    onSubmit = {},
                    onRetryLoad = {},
                    onSkipDay = {},
                    onBack = {},
                )
            }
        }

        compose.onNodeWithTag(AddMealTestTags.SERVINGS).performTextInput("2.5")

        compose.onNodeWithTag(AddMealTestTags.SERVINGS).assert(hasText("2.5"))
        assertEquals("2.5", calls.servings.lastOrNull())
    }

    @Test
    fun `the day menu offers no day and every day of the plan, and reports the choice`() {
        val calls = render(form())

        compose.onNodeWithTag(AddMealTestTags.DAY).assert(hasText(str(R.string.add_meal_day_none)))
        compose.onNodeWithTag(AddMealTestTags.DAY).performClick()

        compose.onNodeWithText("Day 1 · Thursday, October 1, 2026").assertIsDisplayed()
        compose.onNodeWithText("Day 3 · Saturday, October 3, 2026").assertIsDisplayed()
        compose.onNodeWithText("Day 2 · Friday, October 2, 2026").performClick()

        assertEquals(listOf<Int?>(1), calls.days)
    }

    @Test
    fun `the chosen day is shown in the field`() {
        render(form(dayIndex = 2))

        compose.onNodeWithTag(AddMealTestTags.DAY).assert(hasText("Day 3 · Saturday, October 3, 2026"))
    }

    @Test
    fun `without the plan's days there is no day choice`() {
        render(form(days = emptyList()))

        compose.onNodeWithTag(AddMealTestTags.DAY).assertDoesNotExist()
    }

    @Test
    fun `submit reports a tap`() {
        val calls = render(form(mealType = "lunch"))

        compose.onNodeWithTag(AddMealTestTags.SUBMIT).assertIsEnabled().performScrollTo().performClick()

        assertEquals(1, calls.submitted)
    }

    @Test
    fun `field errors appear under their fields`() {
        render(
            form().copy(
                mealTypeError = AddMealFieldError.MEAL_TYPE_REQUIRED,
                servingsError = AddMealFieldError.SERVINGS_INVALID,
            ),
        )

        compose.onNodeWithText(str(R.string.error_add_meal_type_required)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.error_add_meal_servings_invalid)).assertIsDisplayed()
    }

    @Test
    fun `saving disables submit and shows a labelled spinner`() {
        render(form(mealType = "lunch").copy(isSaving = true))

        compose.onNodeWithTag(AddMealTestTags.SUBMIT).assertIsNotEnabled()
        compose.onNodeWithContentDescription(str(R.string.cd_add_meal_saving)).assertExists()
    }

    @Test
    fun `a failed save is announced politely`() {
        render(form(mealType = "lunch").copy(error = AddMealError.NETWORK))

        compose.onNodeWithTag(AddMealTestTags.ERROR_BANNER)
            .assertIsDisplayed()
            .assert(hasLiveRegion())
        compose.onNodeWithText(str(R.string.error_add_meal_network)).assertIsDisplayed()
    }

    @Test
    fun `when only the day failed the form offers a retry and a skip, and locks the meal`() {
        val calls = render(
            form(mealType = "lunch", dayIndex = 1).copy(addedMealId = "m1", error = AddMealError.NETWORK),
        )

        compose.onNodeWithText(str(R.string.error_add_meal_day_not_set)).assertIsDisplayed()
        compose.onNodeWithTag(AddMealTestTags.SUBMIT).assertDoesNotExist()
        compose.onNodeWithTag(AddMealTestTags.SERVINGS).assertIsNotEnabled()
        compose.onNodeWithText(str(R.string.meal_type_lunch)).assertIsNotEnabled()

        compose.onNodeWithTag(AddMealTestTags.RETRY_DAY).performScrollTo().performClick()
        compose.onNodeWithTag(AddMealTestTags.SKIP_DAY).performScrollTo().performClick()

        assertEquals(1, calls.submitted)
        assertEquals(1, calls.skipped)
    }

    @Test
    fun `a failed load offers a retry`() {
        val calls = render(AddMealUiState(isLoading = false, loadError = AddMealError.NETWORK))

        compose.onNodeWithText(str(R.string.error_add_meal_network)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.meal_plans_retry)).performClick()

        assertEquals(1, calls.retriedLoad)
    }

    @Test
    fun `a recipe or plan that no longer exists goes back instead of retrying`() {
        val calls = render(AddMealUiState(isLoading = false, loadError = AddMealError.NOT_FOUND))

        compose.onNodeWithText(str(R.string.error_add_meal_not_found)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.add_meal_back)).performClick()

        assertEquals(0, calls.retriedLoad)
        assertEquals(1, calls.backed)
    }

    @Test
    fun `back is reported`() {
        val calls = render(form())

        compose.onNodeWithContentDescription(str(R.string.cd_meal_plans_back)).performClick()

        assertEquals(1, calls.backed)
    }
}
