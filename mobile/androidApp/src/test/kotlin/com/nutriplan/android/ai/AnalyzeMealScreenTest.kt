package com.nutriplan.android.ai

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.a11y.hasLiveRegion
import com.nutriplan.android.screen.ai.AnalyzeMealScreenContent
import com.nutriplan.android.screen.ai.AnalyzeMealTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.ai.AiError
import com.nutriplan.shared.ai.AnalyzeMealUiState
import com.nutriplan.shared.data.model.MealAnalysis
import com.nutriplan.shared.data.model.NutritionalAlignment
import com.nutriplan.shared.data.model.NutritionalInfo
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * AIA-607: the analyze-meal quick action takes a meal described in words and shows its estimated
 * nutrition, how it fits the targets, any warnings and the disclaimer, with loading and error
 * states. Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
// A tall viewport so every lazily composed list item is on screen.
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2400dp", application = TestApplication::class)
class AnalyzeMealScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private class Calls {
        var analyzed = 0
        var backed = 0
    }

    private fun render(initial: AnalyzeMealUiState): Calls {
        val calls = Calls()
        compose.setContent {
            // Real state so typing is reflected in the field.
            var state by remember { mutableStateOf(initial) }
            NutriPlanTheme {
                AnalyzeMealScreenContent(
                    state = state,
                    onDescriptionChange = { state = state.copy(description = it) },
                    onAnalyze = { calls.analyzed++ },
                    onBack = { calls.backed++ },
                )
            }
        }
        return calls
    }

    private val analysis = MealAnalysis(
        nutritionalInfo = NutritionalInfo(calories = 420, protein = 24.0, carbs = 30.26, fat = 20.0),
        alignment = NutritionalAlignment(score = 72.0, details = "A little high in fat."),
        warnings = listOf("High in saturated fat", "Contains eggs"),
        disclaimer = "Estimates only.",
    )

    private fun analyzed(result: MealAnalysis = analysis) = AnalyzeMealUiState(
        description = "Eggs and toast",
        result = result,
        analyzedDescription = "Eggs and toast",
    )

    @Test
    fun `the title is a heading`() {
        render(AnalyzeMealUiState())

        compose.onNode(isHeading() and hasText(str(R.string.analyze_meal_title))).assertIsDisplayed()
    }

    @Test
    fun `typing a meal and tapping analyze asks for the analysis`() {
        val calls = render(AnalyzeMealUiState())

        compose.onNodeWithTag(AnalyzeMealTestTags.DESCRIPTION).performTextInput("Lentil soup")
        compose.onNodeWithText("Lentil soup").assertExists()
        compose.onNodeWithTag(AnalyzeMealTestTags.SUBMIT).performClick()

        assertEquals(1, calls.analyzed)
    }

    @Test
    fun `the field shows how much can still be typed`() {
        render(AnalyzeMealUiState(description = "Soup"))

        compose.onNodeWithText(str(R.string.analyze_meal_description_count, 4, 500), useUnmergedTree = true)
            .assertExists()
    }

    @Test
    fun `a missing description is reported on the field`() {
        render(AnalyzeMealUiState(descriptionMissing = true))

        compose.onNodeWithText(str(R.string.error_analyze_meal_description_missing), useUnmergedTree = true)
            .assertExists()
    }

    @Test
    fun `while analyzing it shows a labelled progress indicator and the button is disabled`() {
        render(AnalyzeMealUiState(description = "Soup", isAnalyzing = true))

        compose.onNodeWithTag(AnalyzeMealTestTags.LOADING).assertIsDisplayed()
        compose.onNodeWithContentDescription(str(R.string.cd_analyze_meal_loading)).assertExists()
        compose.onNodeWithTag(AnalyzeMealTestTags.SUBMIT).assertIsNotEnabled()
    }

    @Test
    fun `the analysis shows the estimated nutrition of the described meal`() {
        render(analyzed())

        compose.onNodeWithTag(AnalyzeMealTestTags.NUTRITION).assertIsDisplayed()
        compose.onNodeWithTag(AnalyzeMealTestTags.NUTRITION)
            .assert(hasText("Eggs and toast", substring = true))
            .assert(hasText(str(R.string.recipe_kcal, 420), substring = true))
            .assert(hasText(str(R.string.analyze_meal_grams, "24"), substring = true))
            .assert(hasText(str(R.string.analyze_meal_grams, "30.3"), substring = true))
    }

    @Test
    fun `without estimates the nutrition says so`() {
        render(analyzed(analysis.copy(nutritionalInfo = null)))

        compose.onNodeWithText(str(R.string.analyze_meal_nutrition_unknown)).assertExists()
    }

    @Test
    fun `the alignment with the targets is shown when there is one`() {
        render(analyzed())

        compose.onNodeWithTag(AnalyzeMealTestTags.ALIGNMENT).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.ai_recommendations_alignment_score, 72)).assertExists()
    }

    @Test
    fun `no alignment card without targets`() {
        render(analyzed(analysis.copy(alignment = null)))

        compose.onNodeWithTag(AnalyzeMealTestTags.ALIGNMENT).assertDoesNotExist()
    }

    @Test
    fun `every warning is listed`() {
        render(analyzed())

        compose.onAllNodesWithTag(AnalyzeMealTestTags.WARNING).assertCountEquals(2)
        compose.onNodeWithText("High in saturated fat").assertIsDisplayed()
        compose.onNodeWithTag(AnalyzeMealTestTags.NO_WARNINGS).assertDoesNotExist()
    }

    @Test
    fun `no warnings is said plainly`() {
        render(analyzed(analysis.copy(warnings = emptyList())))

        compose.onNodeWithTag(AnalyzeMealTestTags.NO_WARNINGS).assertIsDisplayed()
        compose.onAllNodesWithTag(AnalyzeMealTestTags.WARNING).assertCountEquals(0)
    }

    @Test
    fun `the server disclaimer is shown with the analysis`() {
        render(analyzed())

        compose.onNodeWithTag(AnalyzeMealTestTags.DISCLAIMER).assertIsDisplayed()
        compose.onNodeWithText("Estimates only.").assertIsDisplayed()
    }

    @Test
    fun `without a disclaimer from the server the bundled one is shown`() {
        render(analyzed(analysis.copy(disclaimer = null)))

        compose.onNodeWithText(str(R.string.analyze_meal_disclaimer_fallback)).assertExists()
    }

    @Test
    fun `a failure is announced and the button retries`() {
        val calls = render(AnalyzeMealUiState(description = "Soup", error = AiError.NETWORK))

        compose.onNodeWithTag(AnalyzeMealTestTags.ERROR_BANNER)
            .assert(hasText(str(R.string.error_analyze_meal_network)))
            .assert(hasLiveRegion())
        compose.onNodeWithTag(AnalyzeMealTestTags.SUBMIT).performClick()

        assertEquals(1, calls.analyzed)
    }

    @Test
    fun `back is offered`() {
        val calls = render(AnalyzeMealUiState())

        compose.onNodeWithContentDescription(str(R.string.cd_meal_plans_back)).performClick()

        assertEquals(1, calls.backed)
    }
}
