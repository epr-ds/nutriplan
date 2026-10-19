package com.nutriplan.android.plans

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.a11y.hasLiveRegion
import com.nutriplan.android.screen.plans.MealPlanListScreenContent
import com.nutriplan.android.screen.plans.MealPlanListTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.planning.MealPlanListError
import com.nutriplan.shared.planning.MealPlanListUiState
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * DPL-501: the meal plan list renders every state and stays accessible.
 *
 * Runs on the JVM via Robolectric, so it is a deterministic guard without an emulator.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class MealPlanListScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int): String = context.getString(id)

    private fun plan(id: String) = MealPlanSummary(
        id = id,
        name = "Plan $id",
        startDate = "2026-10-01",
        endDate = "2026-10-07",
        status = "active",
    )

    private fun loaded(vararg ids: String, error: MealPlanListError? = null) = MealPlanListUiState(
        plans = ids.map(::plan),
        isLoading = false,
        error = error,
    )

    private fun render(
        state: MealPlanListUiState,
        onRefresh: () -> Unit = {},
        onRetry: () -> Unit = {},
        onPlanClick: (String) -> Unit = {},
        onCreatePlan: () -> Unit = {},
        onBack: (() -> Unit)? = null,
    ) {
        compose.setContent {
            NutriPlanTheme {
                MealPlanListScreenContent(
                    state = state,
                    onRefresh = onRefresh,
                    onRetry = onRetry,
                    onPlanClick = onPlanClick,
                    onCreatePlan = onCreatePlan,
                    onBack = onBack,
                )
            }
        }
    }

    @Test
    fun `first load shows a labelled progress indicator`() {
        render(MealPlanListUiState())

        compose.onNodeWithTag(MealPlanListTestTags.LOADING).assertIsDisplayed()
        compose.onNodeWithContentDescription(str(R.string.cd_meal_plans_loading)).assertExists()
    }

    @Test
    fun `plans are listed and a tap opens the plan`() {
        var opened: String? = null
        render(loaded("a", "b"), onPlanClick = { opened = it })

        compose.onNodeWithText("Plan a").assertIsDisplayed()
        compose.onNodeWithText("Plan b").assertIsDisplayed()

        compose.onNodeWithText("Plan b").performClick()
        assertEquals("b", opened)
    }

    @Test
    fun `a plan card shows its dates and status in plain language`() {
        render(loaded("a"))

        compose.onNodeWithText("Thursday, October 1, 2026 to Wednesday, October 7, 2026").assertIsDisplayed()
        compose.onNodeWithText(str(R.string.plan_status_active)).assertIsDisplayed()
    }

    @Test
    fun `an unknown status is shown as sent instead of hidden`() {
        render(MealPlanListUiState(plans = listOf(plan("a").copy(status = "archived")), isLoading = false))

        compose.onNodeWithText("archived").assertIsDisplayed()
    }

    @Test
    fun `no plans shows the empty state with a create action`() {
        var created = 0
        render(loaded(), onCreatePlan = { created++ })

        compose.onNodeWithText(str(R.string.meal_plans_empty_title)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.meal_plans_empty_action)).performClick()
        assertEquals(1, created)
    }

    @Test
    fun `failing with nothing saved shows an error with retry`() {
        var retried = 0
        render(loaded(error = MealPlanListError.NETWORK), onRetry = { retried++ })

        compose.onNodeWithText(str(R.string.error_plans_network)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.meal_plans_retry)).performClick()
        assertEquals(1, retried)
    }

    @Test
    fun `failing with saved plans keeps them and announces the problem politely`() {
        render(loaded("a", error = MealPlanListError.SERVER_PROBLEM))

        compose.onNodeWithText("Plan a").assertIsDisplayed()
        compose.onNodeWithTag(MealPlanListTestTags.ERROR_BANNER)
            .assert(hasLiveRegion())
        compose.onNodeWithText(str(R.string.error_plans_server_saved)).assertIsDisplayed()
    }

    @Test
    fun `the create button has a label and a large enough touch target`() {
        var created = 0
        render(loaded("a"), onCreatePlan = { created++ })

        compose.onNodeWithTag(MealPlanListTestTags.CREATE)
            .assertHeightIsAtLeast(48.dp)
            .performClick()
        compose.onNodeWithContentDescription(str(R.string.cd_meal_plans_create)).assertExists()
        assertEquals(1, created)
    }

    @Test
    fun `the title is a heading for screen readers`() {
        render(loaded("a"))

        compose.onNodeWithText(str(R.string.meal_plans_title)).assert(isHeading())
    }

    @Test
    fun `the back button appears only when there is somewhere to go back to`() {
        var backed = 0
        render(loaded("a"), onBack = { backed++ })

        compose.onNodeWithContentDescription(str(R.string.cd_meal_plans_back)).performClick()
        assertEquals(1, backed)
    }

    @Test
    fun `without a back handler there is no back button`() {
        render(loaded("a"), onBack = null)

        compose.onNodeWithContentDescription(str(R.string.cd_meal_plans_back)).assertDoesNotExist()
    }
}
