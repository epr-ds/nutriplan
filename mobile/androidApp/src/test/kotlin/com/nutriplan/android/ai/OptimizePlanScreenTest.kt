package com.nutriplan.android.ai

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
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
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.a11y.hasLiveRegion
import com.nutriplan.android.screen.ai.OptimizePlanScreenContent
import com.nutriplan.android.screen.ai.OptimizePlanTestTags
import com.nutriplan.android.screen.plans.formatPlanDay
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.ai.AiError
import com.nutriplan.shared.ai.MealServingChange
import com.nutriplan.shared.ai.OptimizePlanUiState
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.NutritionalSummary
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * AIA-605: the optimize-plan flow lets the user pick a goal, shows the meals that would change and
 * how the daily average moves, and accepts or discards, with loading, unchanged and error states.
 * Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
// A tall viewport so every lazily composed list item is on screen.
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2400dp", application = TestApplication::class)
class OptimizePlanScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private class Calls {
        val goals = mutableListOf<String>()
        var optimized = 0
        var accepted = 0
        var retries = 0
        var backed = 0
    }

    private fun render(state: OptimizePlanUiState): Calls {
        val calls = Calls()
        compose.setContent {
            NutriPlanTheme {
                OptimizePlanScreenContent(
                    state = state,
                    onGoalChange = { calls.goals += it },
                    onOptimize = { calls.optimized++ },
                    onAccept = { calls.accepted++ },
                    onRetryLoad = { calls.retries++ },
                    onBack = { calls.backed++ },
                )
            }
        }
        return calls
    }

    private val original = MealPlan(
        id = "p1",
        name = "Week",
        startDate = "2026-10-01",
        endDate = "2026-10-07",
        dailyCalorieTarget = 1800,
        status = "active",
        nutritionalSummary = NutritionalSummary(dailyAverage = NutritionalInfo(calories = 1900, protein = 80.0)),
    )

    private val draft = original.copy(
        status = "draft",
        nutritionalSummary = NutritionalSummary(dailyAverage = NutritionalInfo(calories = 1750, protein = 95.4)),
    )

    private val changes = listOf(
        MealServingChange("m1", "breakfast", "Oats", "2026-10-01", before = 1.0, after = 1.5),
        MealServingChange("m3", "dinner", null, null, before = 2.0, after = 1.0),
    )

    private val loaded = OptimizePlanUiState(original = original, isLoadingPlan = false)
    private val proposed = loaded.copy(draft = draft, changes = changes)

    @Test
    fun `the title is a heading`() {
        render(loaded)

        compose.onNode(isHeading() and hasText(str(R.string.optimize_title))).assertIsDisplayed()
    }

    @Test
    fun `loading the plan shows a labelled progress indicator`() {
        render(OptimizePlanUiState())

        compose.onNodeWithTag(OptimizePlanTestTags.PLAN_LOADING).assertIsDisplayed()
        compose.onNodeWithContentDescription(str(R.string.cd_optimize_plan_loading)).assertExists()
    }

    @Test
    fun `a plan that cannot be loaded offers a retry`() {
        val calls = render(OptimizePlanUiState(isLoadingPlan = false, loadError = AiError.NOT_FOUND))

        compose.onNodeWithText(str(R.string.error_optimize_not_found)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.meal_plans_retry)).performClick()

        assertEquals(1, calls.retries)
    }

    @Test
    fun `every goal can be chosen and the chosen one is selected`() {
        val calls = render(loaded)

        compose.onAllNodesWithTag(OptimizePlanTestTags.GOAL_CHIP).assertCountEquals(4)
        compose.onNodeWithText(str(R.string.optimize_goal_balance_macros)).assertIsSelected()
        compose.onNodeWithText(str(R.string.optimize_goal_increase_protein)).performClick()

        assertEquals(listOf("increase_protein"), calls.goals)
    }

    @Test
    fun `the button asks for changes`() {
        val calls = render(loaded)

        compose.onNodeWithTag(OptimizePlanTestTags.SUBMIT).performClick()

        assertEquals(1, calls.optimized)
        compose.onNodeWithTag(OptimizePlanTestTags.ACCEPT).assertDoesNotExist()
    }

    @Test
    fun `while optimizing it shows a labelled progress indicator and the button is disabled`() {
        render(loaded.copy(isOptimizing = true))

        compose.onNodeWithContentDescription(str(R.string.cd_optimize_loading)).assertExists()
        compose.onNodeWithTag(OptimizePlanTestTags.SUBMIT).assertIsNotEnabled()
    }

    @Test
    fun `the proposal lists every changed meal with its servings before and after`() {
        render(proposed)

        compose.onAllNodesWithTag(OptimizePlanTestTags.CHANGE).assertCountEquals(2)
        val breakfast = "${str(R.string.meal_type_breakfast)} · ${formatPlanDay("2026-10-01")}"
        compose.onNodeWithContentDescription(str(R.string.cd_optimize_change, "Oats", breakfast, "1", "1.5"))
            .assertExists()
        val unnamed = str(R.string.plan_detail_meal_unnamed)
        val dinner = str(R.string.meal_type_dinner)
        compose.onNodeWithContentDescription(str(R.string.cd_optimize_change, unnamed, dinner, "2", "1"))
            .assertExists()
    }

    @Test
    fun `the proposal shows how the daily average moves`() {
        render(proposed)

        compose.onNodeWithTag(OptimizePlanTestTags.DAILY).assertIsDisplayed()
        compose.onNodeWithContentDescription(
            str(R.string.cd_optimize_before_after, str(R.string.optimize_daily_calories), "1900", "1750", "kcal"),
        ).assertExists()
        compose.onNodeWithContentDescription(
            str(R.string.cd_optimize_before_after, str(R.string.optimize_daily_protein), "80", "95", "g"),
        ).assertExists()
    }

    @Test
    fun `without summaries the daily average is left out`() {
        render(proposed.copy(draft = draft.copy(nutritionalSummary = null)))

        compose.onNodeWithTag(OptimizePlanTestTags.DAILY).assertDoesNotExist()
        compose.onAllNodesWithTag(OptimizePlanTestTags.CHANGE).assertCountEquals(2)
    }

    @Test
    fun `the proposal can be accepted or discarded and carries the disclaimer`() {
        val calls = render(proposed)

        compose.onNodeWithTag(OptimizePlanTestTags.DISCLAIMER).assertIsDisplayed()
        compose.onNodeWithTag(OptimizePlanTestTags.ACCEPT).performClick()
        compose.onNodeWithTag(OptimizePlanTestTags.DISCARD).performClick()

        assertEquals(1, calls.accepted)
        assertEquals(1, calls.backed)
    }

    @Test
    fun `while saving the actions and goals are disabled`() {
        render(proposed.copy(isAccepting = true))

        compose.onNodeWithTag(OptimizePlanTestTags.ACCEPT).assertIsNotEnabled()
        compose.onNodeWithTag(OptimizePlanTestTags.DISCARD).assertIsNotEnabled()
        compose.onNodeWithTag(OptimizePlanTestTags.SUBMIT).assertIsNotEnabled()
    }

    @Test
    fun `a failed save is announced and accepting again retries`() {
        val calls = render(proposed.copy(acceptError = AiError.NETWORK, appliedMealIds = setOf("m1")))

        compose.onNodeWithTag(OptimizePlanTestTags.ACCEPT_ERROR)
            .assert(hasText(str(R.string.error_optimize_accept_network)))
            .assert(hasLiveRegion())
        compose.onNodeWithTag(OptimizePlanTestTags.ACCEPT).performClick()

        assertEquals(1, calls.accepted)
    }

    @Test
    fun `nothing to change is said plainly with no accept`() {
        render(loaded.copy(draft = original.copy(status = "draft")))

        compose.onNodeWithTag(OptimizePlanTestTags.UNCHANGED).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.optimize_unchanged_title)).assertIsDisplayed()
        compose.onNodeWithTag(OptimizePlanTestTags.ACCEPT).assertDoesNotExist()
    }

    @Test
    fun `an optimization failure is announced`() {
        render(loaded.copy(optimizeError = AiError.REJECTED))

        compose.onNodeWithTag(OptimizePlanTestTags.ERROR_BANNER)
            .assert(hasText(str(R.string.error_optimize_rejected)))
            .assert(hasLiveRegion())
    }
}
