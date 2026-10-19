package com.nutriplan.android.plans

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
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
import com.nutriplan.android.screen.plans.EditMealScreenContent
import com.nutriplan.android.screen.plans.EditMealTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.planning.EditMealError
import com.nutriplan.shared.planning.EditMealFieldError
import com.nutriplan.shared.planning.EditMealUiState
import com.nutriplan.shared.planning.PlanDayOption
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * DPL-508: the edit-meal form changes servings and day, rates the meal 1 to 5, and removes it after
 * a confirmation; every state is reachable and accessible. Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
// A tall viewport so the whole form is on screen.
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2000dp", application = TestApplication::class)
class EditMealScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private val days = listOf(
        PlanDayOption(0, "2026-10-01"),
        PlanDayOption(1, "2026-10-02"),
        PlanDayOption(2, "2026-10-03"),
    )

    private val meal = PlanMeal(
        id = "m1",
        mealType = "lunch",
        servings = 2.0,
        dayIndex = 1,
        satisfactionLevel = null,
        nutritionalInfo = NutritionalInfo(calories = 600),
    )

    private fun form(meal: PlanMeal = this.meal) = EditMealUiState(
        meal = meal,
        days = days,
        isLoading = false,
        servings = "2",
        dayIndex = meal.dayIndex,
        satisfaction = meal.satisfactionLevel,
    )

    private class Calls {
        val servings = mutableListOf<String>()
        val days = mutableListOf<Int?>()
        val ratings = mutableListOf<Int>()
        var saved = 0
        var removed = 0
        var retriedLoad = 0
        var backed = 0
    }

    private fun render(state: EditMealUiState): Calls {
        val calls = Calls()
        compose.setContent {
            NutriPlanTheme {
                EditMealScreenContent(
                    state = state,
                    onServingsChange = { calls.servings += it },
                    onDayChange = { calls.days += it },
                    onSatisfactionChange = { calls.ratings += it },
                    onSave = { calls.saved++ },
                    onRemove = { calls.removed++ },
                    onRetryLoad = { calls.retriedLoad++ },
                    onBack = { calls.backed++ },
                )
            }
        }
        return calls
    }

    @Test
    fun `first load shows a labelled progress indicator`() {
        render(EditMealUiState())

        compose.onNodeWithTag(EditMealTestTags.LOADING).assertIsDisplayed()
        compose.onNodeWithContentDescription(str(R.string.cd_edit_meal_loading)).assertExists()
    }

    @Test
    fun `the title is a heading and the meal is described`() {
        render(form())

        compose.onNode(isHeading() and hasText(str(R.string.edit_meal_title))).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.meal_type_lunch)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.plan_detail_meal_calories, 600)).assertIsDisplayed()
    }

    @Test
    fun `the current servings and day are shown`() {
        render(form())

        compose.onNodeWithTag(EditMealTestTags.SERVINGS).assert(hasText("2"))
        compose.onNodeWithTag(EditMealTestTags.DAY).assert(hasText("Day 2 · Friday, October 2, 2026"))
    }

    @Test
    fun `typing the servings reports the text`() {
        val calls = Calls()
        compose.setContent {
            // Hosted with real state, as in the app: a controlled field only shows what the state holds.
            var state by remember { mutableStateOf(form().copy(servings = "")) }
            NutriPlanTheme {
                EditMealScreenContent(
                    state = state,
                    onServingsChange = { state = state.copy(servings = it); calls.servings += it },
                    onDayChange = {},
                    onSatisfactionChange = {},
                    onSave = {},
                    onRemove = {},
                    onRetryLoad = {},
                    onBack = {},
                )
            }
        }

        compose.onNodeWithTag(EditMealTestTags.SERVINGS).performTextInput("3.5")

        compose.onNodeWithTag(EditMealTestTags.SERVINGS).assert(hasText("3.5"))
        assertEquals("3.5", calls.servings.lastOrNull())
    }

    @Test
    fun `choosing another day reports it`() {
        val calls = render(form())

        compose.onNodeWithTag(EditMealTestTags.DAY).performClick()
        compose.onNodeWithText("Day 3 · Saturday, October 3, 2026").performClick()

        assertEquals(listOf<Int?>(2), calls.days)
    }

    @Test
    fun `a meal that has a day cannot be taken off it`() {
        render(form())

        compose.onNodeWithTag(EditMealTestTags.DAY).performClick()

        compose.onNodeWithText(str(R.string.add_meal_day_none)).assertDoesNotExist()
        compose.onNodeWithText("Day 1 · Thursday, October 1, 2026").assertIsDisplayed()
    }

    @Test
    fun `a meal without a day can be left without one`() {
        render(form(meal.copy(dayIndex = null)))

        compose.onNodeWithTag(EditMealTestTags.DAY).assert(hasText(str(R.string.add_meal_day_none)))
        compose.onNodeWithTag(EditMealTestTags.DAY).performClick()

        // Once in the field, once as the menu entry.
        assertEquals(
            2,
            compose.onAllNodesWithText(str(R.string.add_meal_day_none)).fetchSemanticsNodes().size,
        )
    }

    @Test
    fun `five ratings are offered, described, and the chosen one is selected`() {
        render(form(meal.copy(satisfactionLevel = 3)).copy(satisfaction = 3))

        assertEquals(5, compose.onAllNodesWithTag(EditMealTestTags.SATISFACTION).fetchSemanticsNodes().size)
        compose.onNodeWithContentDescription(str(R.string.edit_meal_satisfaction_value, 3)).assertIsSelected()
        compose.onNodeWithText(str(R.string.edit_meal_satisfaction_unrated)).assertDoesNotExist()
    }

    @Test
    fun `an unrated meal says so, and choosing a rating reports it`() {
        val calls = render(form())

        compose.onNodeWithText(str(R.string.edit_meal_satisfaction_unrated)).assertIsDisplayed()
        compose.onNodeWithContentDescription(str(R.string.edit_meal_satisfaction_value, 5)).performClick()

        assertEquals(listOf(5), calls.ratings)
    }

    @Test
    fun `save reports a tap`() {
        val calls = render(form())

        compose.onNodeWithTag(EditMealTestTags.SAVE).performScrollTo().performClick()

        assertEquals(1, calls.saved)
    }

    @Test
    fun `a servings error appears under the field`() {
        render(form().copy(servingsError = EditMealFieldError.SERVINGS_INVALID))

        compose.onNodeWithText(str(R.string.error_add_meal_servings_invalid)).assertIsDisplayed()
    }

    @Test
    fun `a failed save is announced politely`() {
        render(form().copy(error = EditMealError.NETWORK))

        compose.onNodeWithTag(EditMealTestTags.ERROR_BANNER)
            .assertIsDisplayed()
            .assert(hasLiveRegion())
        compose.onNodeWithText(str(R.string.error_edit_meal_network)).assertIsDisplayed()
    }

    @Test
    fun `while saving the buttons are disabled and a labelled spinner is shown`() {
        render(form().copy(isSaving = true))

        compose.onNodeWithTag(EditMealTestTags.SAVE).assertIsNotEnabled()
        compose.onNodeWithTag(EditMealTestTags.REMOVE).assertIsNotEnabled()
        compose.onNodeWithContentDescription(str(R.string.cd_edit_meal_saving)).assertExists()
    }

    @Test
    fun `removing asks for confirmation first`() {
        val calls = render(form())

        compose.onNodeWithTag(EditMealTestTags.REMOVE).performScrollTo().performClick()
        compose.onNodeWithText(str(R.string.edit_meal_remove_title)).assertIsDisplayed()
        assertEquals(0, calls.removed)

        compose.onNodeWithTag(EditMealTestTags.CONFIRM_REMOVE).performClick()

        assertEquals(1, calls.removed)
        compose.onNodeWithText(str(R.string.edit_meal_remove_title)).assertDoesNotExist()
    }

    @Test
    fun `cancelling the confirmation removes nothing`() {
        val calls = render(form())

        compose.onNodeWithTag(EditMealTestTags.REMOVE).performScrollTo().performClick()
        compose.onNodeWithText(str(R.string.edit_meal_cancel)).performClick()

        assertEquals(0, calls.removed)
        compose.onNodeWithText(str(R.string.edit_meal_remove_title)).assertDoesNotExist()
    }

    @Test
    fun `a failed load offers a retry`() {
        val calls = render(EditMealUiState(isLoading = false, loadError = EditMealError.NETWORK))

        compose.onNodeWithText(str(R.string.error_edit_meal_network)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.meal_plans_retry)).performClick()

        assertEquals(1, calls.retriedLoad)
    }

    @Test
    fun `a meal that no longer exists goes back instead of retrying`() {
        val calls = render(EditMealUiState(isLoading = false, loadError = EditMealError.NOT_FOUND))

        compose.onNodeWithText(str(R.string.error_edit_meal_not_found)).assertIsDisplayed()
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
