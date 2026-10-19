package com.nutriplan.android.plans

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.a11y.hasLiveRegion
import com.nutriplan.android.screen.plans.MealPlanFormScreenContent
import com.nutriplan.android.screen.plans.MealPlanFormTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.planning.MealPlanFormError
import com.nutriplan.shared.planning.MealPlanFormUiState
import com.nutriplan.shared.planning.PlanFieldError
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * DPL-503: the create-plan form shows its fields, errors and prefill note, and stays accessible.
 * Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
// A tall viewport so the whole form is on screen.
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2000dp", application = TestApplication::class)
class MealPlanFormScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int): String = context.getString(id)

    private val filled = MealPlanFormUiState(
        name = "Week 40",
        startDate = "2026-10-01",
        endDate = "2026-10-07",
        calories = "2000",
    )

    private class Calls {
        val names = mutableListOf<String>()
        val starts = mutableListOf<String>()
        val ends = mutableListOf<String>()
        val calories = mutableListOf<String>()
        var submitted = 0
        var backed = 0
    }

    private fun render(state: MealPlanFormUiState, calls: Calls = Calls()): Calls {
        compose.setContent {
            NutriPlanTheme {
                MealPlanFormScreenContent(
                    state = state,
                    onNameChange = { calls.names += it },
                    onStartDateChange = { calls.starts += it },
                    onEndDateChange = { calls.ends += it },
                    onCaloriesChange = { calls.calories += it },
                    onSubmit = { calls.submitted++ },
                    onBack = { calls.backed++ },
                )
            }
        }
        return calls
    }

    @Test
    fun `shows the title as a heading and every field with its value`() {
        render(filled)

        compose.onNodeWithText(str(R.string.plan_form_title)).assert(isHeading())
        compose.onNodeWithTag(MealPlanFormTestTags.NAME).assert(hasText("Week 40"))
        compose.onNodeWithTag(MealPlanFormTestTags.START_DATE).assert(hasText("Thursday, October 1, 2026"))
        compose.onNodeWithTag(MealPlanFormTestTags.END_DATE).assert(hasText("Wednesday, October 7, 2026"))
        compose.onNodeWithTag(MealPlanFormTestTags.CALORIES).assert(hasText("2000"))
        compose.onNodeWithTag(MealPlanFormTestTags.SUBMIT).assertIsDisplayed().assertIsEnabled()
    }

    @Test
    fun `typing reports each field change`() {
        val calls = render(MealPlanFormUiState())

        compose.onNodeWithTag(MealPlanFormTestTags.NAME).performTextInput("Plan")
        compose.onNodeWithTag(MealPlanFormTestTags.CALORIES).performTextInput("1800")

        assertEquals(listOf("Plan"), calls.names)
        assertEquals(listOf("1800"), calls.calories)
    }

    @Test
    fun `submit calls back and has a large enough touch target`() {
        val calls = render(filled)

        compose.onNodeWithTag(MealPlanFormTestTags.SUBMIT)
            .assertHeightIsAtLeast(48.dp)
            .performScrollTo()
            .performClick()

        assertEquals(1, calls.submitted)
    }

    @Test
    fun `inline errors appear under their fields`() {
        render(
            filled.copy(
                name = "",
                endDate = "2026-09-30",
                calories = "",
                nameError = PlanFieldError.NAME_REQUIRED,
                endDateError = PlanFieldError.END_BEFORE_START,
                caloriesError = PlanFieldError.CALORIES_REQUIRED,
            ),
        )

        compose.onNodeWithText(str(R.string.error_plan_name_required)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.error_plan_end_before_start)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.error_plan_calories_required)).assertIsDisplayed()
    }

    @Test
    fun `a prefilled calorie target says where it came from`() {
        render(filled.copy(caloriesPrefilled = true))

        compose.onNodeWithText(str(R.string.plan_form_calories_prefilled)).assertIsDisplayed()
    }

    @Test
    fun `an error on the calories replaces the prefill note`() {
        render(filled.copy(caloriesPrefilled = true, caloriesError = PlanFieldError.CALORIES_INVALID))

        compose.onNodeWithText(str(R.string.error_plan_calories_invalid)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.plan_form_calories_prefilled)).assertDoesNotExist()
    }

    @Test
    fun `a failed save is announced politely and keeps the form`() {
        render(filled.copy(error = MealPlanFormError.NETWORK))

        compose.onNodeWithTag(MealPlanFormTestTags.ERROR_BANNER).assert(hasLiveRegion())
        compose.onNodeWithText(str(R.string.error_plan_form_network)).assertIsDisplayed()
        compose.onNodeWithTag(MealPlanFormTestTags.NAME).assert(hasText("Week 40"))
    }

    @Test
    fun `while saving the button is disabled and labelled`() {
        render(filled.copy(isSaving = true))

        compose.onNodeWithTag(MealPlanFormTestTags.SUBMIT).assertIsNotEnabled()
        compose.onNodeWithContentDescription(str(R.string.cd_plan_form_saving)).assertExists()
    }

    @Test
    fun `tapping a date opens the date picker, and cancelling leaves the date alone`() {
        val calls = render(filled)

        compose.onNodeWithTag(MealPlanFormTestTags.START_DATE).performClick()
        compose.onNodeWithText(context.getString(android.R.string.cancel)).assertIsDisplayed()
        compose.onNodeWithText(context.getString(android.R.string.cancel)).performClick()

        assertEquals(emptyList<String>(), calls.starts)
    }

    @Test
    fun `confirming the date picker keeps the selected date`() {
        val calls = render(filled)

        compose.onNodeWithTag(MealPlanFormTestTags.END_DATE).performClick()
        compose.onNodeWithText(context.getString(android.R.string.ok)).performClick()

        // The picker opens on the field's current day (Oct 7); confirming without changing it reports it.
        assertEquals(listOf("2026-10-07"), calls.ends)
    }

    @Test
    fun `the back button works`() {
        val calls = render(filled)

        compose.onNodeWithContentDescription(str(R.string.cd_meal_plans_back)).performClick()

        assertEquals(1, calls.backed)
    }
}
