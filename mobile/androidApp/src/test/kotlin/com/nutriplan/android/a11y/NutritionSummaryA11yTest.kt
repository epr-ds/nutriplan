package com.nutriplan.android.a11y

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.screen.plans.NutritionSummaryCard
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.model.NutritionalSummary
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.NutritionalTargets
import com.nutriplan.shared.data.model.NutritionalProgress
import com.nutriplan.shared.data.model.NutrientProgress
import com.nutriplan.shared.planning.toNutritionSummaryUi
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * DPL-707: screen-reader regression checks for the planning + nutrition progress visuals.
 *
 * The nutrition summary draws a calorie ring and macro bars against the plan's daily targets,
 * with the status in words. What the screen reader hears, though, must come from the progress
 * visuals themselves: a TalkBack / VoiceOver user cannot infer "90% of target" from an unnamed
 * progress indicator, so the announcement has to be part of the semantics. Runs on the JVM via
 * Robolectric, so the checks are deterministic without an emulator.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2000dp", application = TestApplication::class)
class NutritionSummaryA11yTest {

    @get:Rule
    val compose = createComposeRule()

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
            NutriPlanTheme {
                NutritionSummaryCard(summary.toNutritionSummaryUi())
            }
        }
        compose.waitForIdle()
    }

    @Test
    fun `nutrition summary progress visuals announce their progress to screen readers`() {
        render(summary)

        // The calorie ring: 90% of the 2,000 kcal target.
        compose.onNodeWithContentDescription("Calories: 90% of target").assertIsDisplayed()
    }
}