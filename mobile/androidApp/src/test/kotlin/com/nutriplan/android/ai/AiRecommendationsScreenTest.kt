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
import androidx.compose.ui.test.assertIsSelected
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
import com.nutriplan.android.screen.ai.AiRecommendationsScreenContent
import com.nutriplan.android.screen.ai.AiRecommendationsTestTags
import com.nutriplan.android.screen.recipes.RecipeSearchTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.ai.AiError
import com.nutriplan.shared.ai.AiRecommendationsUiState
import com.nutriplan.shared.data.model.AiRecommendations
import com.nutriplan.shared.data.model.NutritionalAlignment
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.Recipe
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * AIA-602: the AI recommendations screen shows the recommended recipes with their macros, why they
 * were picked, how well they fit the targets and the disclaimer, with loading, empty and error
 * states. Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
// A tall viewport so every lazily composed list item is on screen.
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2400dp", application = TestApplication::class)
class AiRecommendationsScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private class Calls {
        val mealTypes = mutableListOf<String?>()
        val opened = mutableListOf<String>()
        var requests = 0
        var backed = 0
    }

    private fun render(initial: AiRecommendationsUiState): Calls {
        val calls = Calls()
        compose.setContent {
            // Real state so typing is reflected in the field.
            var state by remember { mutableStateOf(initial) }
            NutriPlanTheme {
                AiRecommendationsScreenContent(
                    state = state,
                    onMealTypeChange = {
                        calls.mealTypes += it
                        state = state.copy(mealType = it)
                    },
                    onIngredientsChange = { state = state.copy(ingredients = it) },
                    onRecommend = { calls.requests++ },
                    onRecipeClick = { calls.opened += it },
                    onBack = { calls.backed++ },
                )
            }
        }
        return calls
    }

    private fun answered(result: AiRecommendations) = AiRecommendationsUiState(result = result, hasRequested = true)

    private val answer = AiRecommendations(
        recommendations = listOf(
            Recipe(
                id = "r1",
                name = "Tofu bowl",
                imageUrl = "https://img.example/tofu.jpg",
                nutritionalInfo = NutritionalInfo(calories = 520, protein = 32.0),
            ),
            Recipe(id = "r2", name = "Lentil soup"),
        ),
        reasoning = "High in plant protein and within your calories.",
        nutritionalAlignment = NutritionalAlignment(score = 86.4, details = "Close to your protein target."),
        disclaimer = "Not medical advice.",
    )

    @Test
    fun `the title is a heading`() {
        render(answered(answer))

        compose.onNode(isHeading() and hasText(str(R.string.ai_recommendations_title))).assertIsDisplayed()
    }

    @Test
    fun `before the first answer it shows a labelled progress indicator`() {
        render(AiRecommendationsUiState())

        compose.onNodeWithTag(AiRecommendationsTestTags.LOADING).assertIsDisplayed()
        compose.onNodeWithContentDescription(str(R.string.cd_ai_recommendations_loading)).assertExists()
        compose.onNodeWithTag(AiRecommendationsTestTags.EMPTY).assertDoesNotExist()
    }

    @Test
    fun `while a request runs the button is disabled`() {
        render(AiRecommendationsUiState(isLoading = true, hasRequested = true))

        compose.onNodeWithTag(AiRecommendationsTestTags.SUBMIT).assertIsNotEnabled()
        compose.onNodeWithTag(AiRecommendationsTestTags.LOADING).assertIsDisplayed()
    }

    @Test
    fun `the recommended recipes are listed with their macros and open on tap`() {
        val calls = render(answered(answer))

        compose.onAllNodesWithTag(RecipeSearchTestTags.RECIPE_CARD).assertCountEquals(2)
        compose.onNodeWithText("Tofu bowl").assertIsDisplayed()
        compose.onNodeWithText(
            "${str(R.string.recipe_kcal, 520)} · ${str(R.string.recipe_protein_g, "32")}",
        ).assertIsDisplayed()

        compose.onNodeWithText("Lentil soup").performClick()
        assertEquals(listOf("r2"), calls.opened)
    }

    @Test
    fun `the reasoning and the alignment score are shown`() {
        render(answered(answer))

        compose.onNodeWithTag(AiRecommendationsTestTags.REASONING).assertIsDisplayed()
        compose.onNodeWithText("High in plant protein and within your calories.").assertIsDisplayed()
        compose.onNodeWithTag(AiRecommendationsTestTags.ALIGNMENT).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.ai_recommendations_alignment_score, 86)).assertIsDisplayed()
        compose.onNodeWithText("Close to your protein target.").assertIsDisplayed()
    }

    @Test
    fun `curated fallback recipes are labelled as such`() {
        render(answered(answer.copy(source = AiRecommendations.SOURCE_CURATED_FALLBACK)))

        compose.onNodeWithTag(AiRecommendationsTestTags.CURATED_FALLBACK_NOTE).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.ai_recommendations_curated_fallback_title)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.ai_recommendations_curated_fallback_body)).assertIsDisplayed()
        compose.onAllNodesWithTag(RecipeSearchTestTags.RECIPE_CARD).assertCountEquals(2)
    }

    @Test
    fun `the model's own answer has no curated note`() {
        render(answered(answer.copy(source = AiRecommendations.SOURCE_MODEL)))

        compose.onNodeWithTag(AiRecommendationsTestTags.CURATED_FALLBACK_NOTE).assertDoesNotExist()
    }

    @Test
    fun `an answer without a source has no curated note`() {
        render(answered(answer.copy(source = null)))

        compose.onNodeWithTag(AiRecommendationsTestTags.CURATED_FALLBACK_NOTE).assertDoesNotExist()
    }

    @Test
    fun `an empty curated fallback shows the empty state without the note`() {
        render(answered(AiRecommendations(source = AiRecommendations.SOURCE_CURATED_FALLBACK)))

        compose.onNodeWithTag(AiRecommendationsTestTags.EMPTY).assertIsDisplayed()
        compose.onNodeWithTag(AiRecommendationsTestTags.CURATED_FALLBACK_NOTE).assertDoesNotExist()
    }

    @Test
    fun `no alignment card when there were no targets`() {
        render(answered(answer.copy(nutritionalAlignment = null)))

        compose.onNodeWithTag(AiRecommendationsTestTags.ALIGNMENT).assertDoesNotExist()
    }

    @Test
    fun `the server disclaimer is shown with the answer`() {
        render(answered(answer))

        compose.onNodeWithTag(AiRecommendationsTestTags.DISCLAIMER).assertIsDisplayed()
        compose.onNodeWithText("Not medical advice.").assertIsDisplayed()
    }

    @Test
    fun `without a disclaimer from the server the bundled one is shown`() {
        render(answered(answer.copy(disclaimer = null)))

        compose.onNodeWithText(str(R.string.ai_disclaimer_fallback)).assertIsDisplayed()
    }

    @Test
    fun `an answer without recipes is the empty state with the disclaimer`() {
        render(answered(AiRecommendations(reasoning = "Nothing fits.")))

        compose.onNodeWithTag(AiRecommendationsTestTags.EMPTY).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.ai_recommendations_empty_title)).assertIsDisplayed()
        compose.onNodeWithTag(AiRecommendationsTestTags.DISCLAIMER).assertIsDisplayed()
    }

    @Test
    fun `a failure is announced and the button retries`() {
        val calls = render(AiRecommendationsUiState(error = AiError.NETWORK, hasRequested = true))

        compose.onNodeWithTag(AiRecommendationsTestTags.ERROR_BANNER)
            .assert(hasText(str(R.string.error_ai_network)))
            .assert(hasLiveRegion())
        compose.onNodeWithTag(AiRecommendationsTestTags.LOADING).assertDoesNotExist()
        compose.onNodeWithTag(AiRecommendationsTestTags.EMPTY).assertDoesNotExist()

        compose.onNodeWithTag(AiRecommendationsTestTags.SUBMIT).performClick()
        assertEquals(1, calls.requests)
    }

    @Test
    fun `every error has its own message`() {
        val expected = mapOf(
            AiError.SERVER_PROBLEM to R.string.error_ai_server,
            AiError.SESSION_EXPIRED to R.string.error_ai_session_expired,
            AiError.REJECTED to R.string.error_ai_rejected,
            AiError.NOT_FOUND to R.string.error_ai_unknown,
            AiError.UNKNOWN to R.string.error_ai_unknown,
        )
        var state by mutableStateOf(AiRecommendationsUiState(hasRequested = true))
        compose.setContent {
            NutriPlanTheme {
                AiRecommendationsScreenContent(state, {}, {}, {}, {}, {})
            }
        }

        expected.forEach { (error, message) ->
            state = AiRecommendationsUiState(error = error, hasRequested = true)
            compose.onNodeWithTag(AiRecommendationsTestTags.ERROR_BANNER).assert(hasText(str(message)))
        }
    }

    @Test
    fun `choosing a meal type selects its chip`() {
        val calls = render(answered(answer))

        compose.onNodeWithText(str(R.string.meal_type_dinner)).performClick()

        assertEquals(listOf<String?>("dinner"), calls.mealTypes)
        compose.onNodeWithText(str(R.string.meal_type_dinner)).assertIsSelected()
    }

    @Test
    fun `typed ingredients are kept and the button asks again`() {
        val calls = render(answered(answer))

        compose.onNodeWithTag(AiRecommendationsTestTags.INGREDIENTS).performTextInput("rice, tofu")
        compose.onNodeWithText("rice, tofu").assertExists()
        compose.onNodeWithTag(AiRecommendationsTestTags.SUBMIT).performClick()

        assertEquals(1, calls.requests)
    }

    @Test
    fun `back is offered`() {
        val calls = render(answered(answer))

        compose.onNodeWithContentDescription(str(R.string.cd_meal_plans_back)).performClick()

        assertEquals(1, calls.backed)
    }

    // --- AIA-604: add a recommendation to a plan ---

    private fun renderAdding(state: AiRecommendationsUiState, mealAdded: Boolean = false): MutableList<String> {
        val added = mutableListOf<String>()
        compose.setContent {
            NutriPlanTheme {
                AiRecommendationsScreenContent(
                    state = state,
                    onMealTypeChange = {},
                    onIngredientsChange = {},
                    onRecommend = {},
                    onRecipeClick = {},
                    onBack = {},
                    onAddToPlan = { added += it.id },
                    mealAdded = mealAdded,
                )
            }
        }
        return added
    }

    @Test
    fun `every recommendation can be added to a plan`() {
        val added = renderAdding(answered(answer))

        compose.onAllNodesWithTag(AiRecommendationsTestTags.ADD_TO_PLAN).assertCountEquals(2)
        val addSoup = str(R.string.cd_ai_recommendations_add_to_plan, "Lentil soup")
        compose.onNodeWithContentDescription(addSoup).performClick()

        assertEquals(listOf("r2"), added)
    }

    @Test
    fun `without the add action there is no add button`() {
        render(answered(answer))

        compose.onAllNodesWithTag(AiRecommendationsTestTags.ADD_TO_PLAN).assertCountEquals(0)
    }

    @Test
    fun `an added recommendation is confirmed and announced`() {
        renderAdding(answered(answer), mealAdded = true)

        compose.onNodeWithTag(AiRecommendationsTestTags.ADDED_NOTICE)
            .assert(hasText(str(R.string.ai_recommendations_added)))
            .assert(hasLiveRegion())
    }

    @Test
    fun `no confirmation until something was added`() {
        renderAdding(answered(answer))

        compose.onNodeWithTag(AiRecommendationsTestTags.ADDED_NOTICE).assertDoesNotExist()
    }
}
