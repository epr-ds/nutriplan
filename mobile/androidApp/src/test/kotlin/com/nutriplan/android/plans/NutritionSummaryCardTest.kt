package com.nutriplan.android.plans

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.screen.plans.NutritionSummaryCard
import com.nutriplan.android.screen.plans.NutritionSummaryTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.model.NutrientProgress
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.NutritionalProgress
import com.nutriplan.shared.data.model.NutritionalSummary
import com.nutriplan.shared.data.model.NutritionalTargets
import com.nutriplan.shared.planning.toNutritionSummaryUi
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * DPL-605 / DPL-606: the nutrition card draws the daily average against its targets (a ring for
 * calories, bars for macros) with the status in words, and the plan total. Runs on the JVM via
 * Robolectric.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2000dp", application = TestApplication::class)
class NutritionSummaryCardTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private val summary = NutritionalSummary(
        total = NutritionalInfo(calories = 12600, protein = 630.0, carbs = 1400.0, fat = 420.0),
        dailyAverage = NutritionalInfo(calories = 1800, protein = 90.0, carbs = 200.0, fat = 60.5),
        targets = NutritionalTargets(calories = 2000, protein = 90, carbs = 180, fat = 70),
        progress = NutritionalProgress(
            calories = NutrientProgress(2000.0, 1800.0, 90.0, "under"),
            protein = NutrientProgress(90.0, 90.0, 100.0, "on_target"),
            carbs = NutrientProgress(180.0, 200.0, 111.1, "over"),
            fat = NutrientProgress(70.0, 60.5, 86.4, "under"),
        ),
    )

    private fun render(summary: NutritionalSummary?) {
        compose.setContent {
            NutriPlanTheme { NutritionSummaryCard(summary.toNutritionSummaryUi()) }
        }
    }

    @Test
    fun `nothing is drawn without data`() {
        render(null)

        compose.onNodeWithTag(NutritionSummaryTestTags.CARD).assertDoesNotExist()
    }

    @Test
    fun `targets without any average draw nothing`() {
        render(NutritionalSummary(targets = NutritionalTargets(calories = 2000)))

        compose.onNodeWithTag(NutritionSummaryTestTags.CARD).assertDoesNotExist()
    }

    @Test
    fun `the card has a title and one row per nutrient, calories as a ring and macros as bars`() {
        render(summary)

        compose.onNodeWithText(str(R.string.nutrition_title)).assertIsDisplayed()
        assertEquals(4, compose.onAllNodesWithTag(NutritionSummaryTestTags.ROW).fetchSemanticsNodes().size)
        assertEquals(1, compose.onAllNodesWithTag(NutritionSummaryTestTags.RING, useUnmergedTree = true).fetchSemanticsNodes().size)
        assertEquals(3, compose.onAllNodesWithTag(NutritionSummaryTestTags.BAR, useUnmergedTree = true).fetchSemanticsNodes().size)
    }

    @Test
    fun `each row says the average against the target`() {
        render(summary)

        compose.onNodeWithText(str(R.string.nutrition_kcal_of_target, "1,800", "2,000")).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.nutrition_g_of_target, "90", "90")).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.nutrition_g_of_target, "200", "180")).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.nutrition_g_of_target, "60.5", "70")).assertIsDisplayed()
    }

    @Test
    fun `over, on target and under are told apart in words`() {
        render(summary)

        // Calories and fat are under, protein is on target, carbs are over.
        assertEquals(2, compose.onAllNodesWithText(str(R.string.nutrition_status_under)).fetchSemanticsNodes().size)
        assertEquals(1, compose.onAllNodesWithText(str(R.string.nutrition_status_on_target)).fetchSemanticsNodes().size)
        assertEquals(1, compose.onAllNodesWithText(str(R.string.nutrition_status_over)).fetchSemanticsNodes().size)
    }

    @Test
    fun `the calorie ring shows its percentage`() {
        render(summary)

        compose.onNodeWithText(str(R.string.nutrition_percent, 90)).assertIsDisplayed()
    }

    @Test
    fun `the plan total lists the nutrients the plan has totals for`() {
        render(summary)

        compose.onNodeWithTag(NutritionSummaryTestTags.TOTAL).assertIsDisplayed()
        compose.onNodeWithText(
            str(R.string.nutrition_total, "12,600 kcal · Protein 630 g · Carbs 1,400 g · Fat 420 g"),
        ).assertIsDisplayed()
    }

    @Test
    fun `a nutrient without a target says so instead of showing a percentage`() {
        render(NutritionalSummary(dailyAverage = NutritionalInfo(calories = 1800, protein = 80.0)))

        compose.onNodeWithText(str(R.string.nutrition_g, "80")).assertIsDisplayed()
        assertEquals(2, compose.onAllNodesWithText(str(R.string.nutrition_status_no_target)).fetchSemanticsNodes().size)
    }

    @Test
    fun `a target with no average yet says there is not enough data`() {
        render(
            NutritionalSummary(
                dailyAverage = NutritionalInfo(calories = 1800),
                targets = NutritionalTargets(calories = 2000, protein = 90),
            ),
        )

        compose.onNodeWithText(str(R.string.nutrition_no_data)).assertExists()
    }

    @Test
    fun `without totals there is no total line`() {
        render(summary.copy(total = null))

        compose.onNodeWithTag(NutritionSummaryTestTags.TOTAL).assertDoesNotExist()
    }
}
