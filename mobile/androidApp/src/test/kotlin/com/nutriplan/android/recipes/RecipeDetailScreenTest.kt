package com.nutriplan.android.recipes

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasText
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
import com.nutriplan.android.screen.recipes.RecipeDetailScreenContent
import com.nutriplan.android.screen.recipes.RecipeDetailTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.model.NutritionDisclaimer
import com.nutriplan.shared.data.model.NutritionSource
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.model.RecipeIngredient
import com.nutriplan.shared.recipes.RecipeDetailError
import com.nutriplan.shared.recipes.RecipeDetailUiState
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * DPL-603: the recipe detail shows ingredients, steps and nutrition per serving, and the nutrition
 * disclaimer is always shown with it (the server's text, or the bundled one when that did not
 * load). Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
// A tall viewport so the whole page is on screen.
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2000dp", application = TestApplication::class)
class RecipeDetailScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private val recipe = Recipe(
        id = "r1",
        name = "Chicken bowl",
        description = "A quick weeknight bowl.",
        ingredients = listOf(
            RecipeIngredient(name = "chicken breast", quantity = 200.0, unit = "g"),
            RecipeIngredient(name = "egg", quantity = 2.0),
            RecipeIngredient(name = "salt"),
        ),
        instructions = listOf("Cook the chicken.", "Serve."),
        prepTime = 10,
        cookTime = 20,
        servings = 2,
        dietaryTypes = listOf("keto", "mystery-diet"),
        nutritionalInfo = NutritionalInfo(calories = 520, protein = 32.5, carbs = 40.0, fat = 18.0, sugar = 4.0),
    )

    private val disclaimer = NutritionDisclaimer(
        disclaimer = "Server disclaimer text.",
        sources = listOf(
            NutritionSource("usda", "USDA FoodData Central", "https://fdc.nal.usda.gov", verified = true),
            NutritionSource("local", "Local table", "not-a-link", verified = false),
        ),
        lastReviewed = "2026-09-01",
    )

    private fun loaded(disclaimer: NutritionDisclaimer? = null, recipe: Recipe = this.recipe) =
        RecipeDetailUiState(recipe = recipe, disclaimer = disclaimer, isLoading = false)

    private fun render(
        state: RecipeDetailUiState,
        onRetry: () -> Unit = {},
        onBack: () -> Unit = {},
    ) {
        compose.setContent {
            NutriPlanTheme {
                RecipeDetailScreenContent(state = state, onRetry = onRetry, onBack = onBack)
            }
        }
    }

    @Test
    fun `first load shows a labelled progress indicator`() {
        render(RecipeDetailUiState())

        compose.onNodeWithTag(RecipeDetailTestTags.LOADING).assertIsDisplayed()
        compose.onNodeWithContentDescription(str(R.string.cd_recipe_loading)).assertExists()
    }

    @Test
    fun `the recipe name is the heading and the overview is shown`() {
        render(loaded())

        compose.onNode(isHeading() and hasText("Chicken bowl")).assertIsDisplayed()
        compose.onNodeWithText("A quick weeknight bowl.").assertIsDisplayed()
        compose.onNodeWithText("Prep 10 min · Cook 20 min · 2 servings").assertIsDisplayed()
    }

    @Test
    fun `diet types are shown, localized when known and as sent otherwise`() {
        render(loaded())

        compose.onNodeWithText(str(R.string.diet_keto)).assertIsDisplayed()
        compose.onNodeWithText("mystery-diet").assertIsDisplayed()
    }

    @Test
    fun `ingredients show the amount only when it is known`() {
        render(loaded())

        compose.onNodeWithText("200 g chicken breast").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("2 egg").assertIsDisplayed()
        compose.onNodeWithText("salt").assertIsDisplayed()
        assertEquals(3, compose.onAllNodesWithTag(RecipeDetailTestTags.INGREDIENT).fetchSemanticsNodes().size)
    }

    @Test
    fun `instructions are numbered`() {
        render(loaded())

        compose.onNodeWithText("1. Cook the chicken.").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("2. Serve.").assertIsDisplayed()
    }

    @Test
    fun `nutrition per serving shows every value`() {
        render(loaded())

        compose.onNodeWithTag(RecipeDetailTestTags.NUTRITION).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.recipe_detail_nutrition_title)).assertIsDisplayed()
        compose.onNodeWithText("520 kcal").assertIsDisplayed()
        compose.onNodeWithText("Protein 32.5 g").assertIsDisplayed()
        compose.onNodeWithText("Carbs 40 g").assertIsDisplayed()
        compose.onNodeWithText("Fat 18 g").assertIsDisplayed()
        compose.onNodeWithText("Sugar 4 g").assertIsDisplayed()
    }

    @Test
    fun `the server disclaimer, its sources and review date are shown when loaded`() {
        render(loaded(disclaimer = disclaimer))

        compose.onNodeWithText("Server disclaimer text.").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText(str(R.string.recipe_disclaimer_fallback)).assertDoesNotExist()
        compose.onNodeWithText(str(R.string.recipe_disclaimer_source_verified, "USDA FoodData Central"))
            .assertIsDisplayed()
        compose.onNodeWithText("Local table").assertIsDisplayed()
        compose.onNodeWithText(str(R.string.recipe_disclaimer_reviewed, "2026-09-01")).assertIsDisplayed()
    }

    @Test
    fun `only web sources are links`() {
        render(loaded(disclaimer = disclaimer))

        assertEquals(1, compose.onAllNodesWithTag(RecipeDetailTestTags.SOURCE).fetchSemanticsNodes().size)
    }

    @Test
    fun `the bundled disclaimer is shown next to the nutrition when the server one did not load`() {
        render(loaded(disclaimer = null))

        compose.onNodeWithTag(RecipeDetailTestTags.NUTRITION).assertIsDisplayed()
        compose.onNodeWithTag(RecipeDetailTestTags.DISCLAIMER).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.recipe_disclaimer_fallback)).assertIsDisplayed()
    }

    @Test
    fun `a recipe without nutrition shows no nutrition card`() {
        render(loaded(recipe = recipe.copy(nutritionalInfo = null)))

        compose.onNodeWithTag(RecipeDetailTestTags.NUTRITION).assertDoesNotExist()
    }

    @Test
    fun `a sparse recipe renders with only its name`() {
        render(loaded(recipe = Recipe(id = "r2", name = "Mystery stew")))

        compose.onNode(isHeading() and hasText("Mystery stew")).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.recipe_detail_ingredients)).assertDoesNotExist()
        compose.onNodeWithText(str(R.string.recipe_detail_instructions)).assertDoesNotExist()
    }

    @Test
    fun `a failed load offers a retry`() {
        var retries = 0
        render(
            RecipeDetailUiState(isLoading = false, error = RecipeDetailError.NETWORK),
            onRetry = { retries++ },
        )

        compose.onNodeWithText(str(R.string.error_recipe_detail_network)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.meal_plans_retry)).performClick()

        assertEquals(1, retries)
    }

    @Test
    fun `a recipe that no longer exists goes back instead of retrying`() {
        var retries = 0
        var back = 0
        render(
            RecipeDetailUiState(isLoading = false, error = RecipeDetailError.NOT_FOUND),
            onRetry = { retries++ },
            onBack = { back++ },
        )

        compose.onNodeWithText(str(R.string.error_recipe_detail_not_found)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.recipe_detail_back_to_recipes)).performClick()

        assertEquals(0, retries)
        assertEquals(1, back)
    }

    @Test
    fun `back is reported`() {
        var back = 0
        render(loaded(), onBack = { back++ })

        compose.onNodeWithContentDescription(str(R.string.cd_meal_plans_back)).performClick()

        assertEquals(1, back)
    }
}
