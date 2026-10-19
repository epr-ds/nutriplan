package com.nutriplan.android.recipes

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.a11y.hasLiveRegion
import com.nutriplan.android.screen.recipes.FavoriteRecipesScreenContent
import com.nutriplan.android.screen.recipes.FavoriteRecipesTestTags
import com.nutriplan.android.screen.recipes.FavoriteTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.recipes.FavoriteError
import com.nutriplan.shared.recipes.FavoriteRecipesUiState
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * DPL-607: the favorites list shows the saved recipes, works from the copy on the device when
 * offline, and removes a favorite with its heart. Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
// A tall viewport so every lazily composed list item is on screen.
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2000dp", application = TestApplication::class)
class FavoriteRecipesScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private fun recipe(id: String, name: String, calories: Int? = null) = Recipe(
        id = id,
        name = name,
        nutritionalInfo = calories?.let { NutritionalInfo(calories = it) },
    )

    private class Calls {
        val opened = mutableListOf<String>()
        val toggled = mutableListOf<String>()
        var retries = 0
        var backed = 0
    }

    private fun render(state: FavoriteRecipesUiState): Calls {
        val calls = Calls()
        compose.setContent {
            NutriPlanTheme {
                FavoriteRecipesScreenContent(
                    state = state,
                    onRecipeClick = { calls.opened += it },
                    onToggleFavorite = { calls.toggled += it.id },
                    onRetry = { calls.retries++ },
                    onBack = { calls.backed++ },
                )
            }
        }
        return calls
    }

    private fun loaded(vararg recipes: Recipe, offline: Boolean = false) =
        FavoriteRecipesUiState(recipes = recipes.toList(), hasLoaded = true, isOffline = offline)

    @Test
    fun `the title is a heading`() {
        render(loaded())

        compose.onNode(isHeading() and hasText(str(R.string.favorites_title))).assertIsDisplayed()
    }

    @Test
    fun `the first load shows a labelled progress indicator`() {
        render(FavoriteRecipesUiState(isLoading = true))

        compose.onNodeWithTag(FavoriteRecipesTestTags.LOADING).assertIsDisplayed()
        compose.onNodeWithContentDescription(str(R.string.cd_favorites_loading)).assertExists()
    }

    @Test
    fun `before the load has even started it does not claim there are no favorites`() {
        render(FavoriteRecipesUiState())

        compose.onNodeWithText(str(R.string.favorites_empty_title)).assertDoesNotExist()
        compose.onNodeWithTag(FavoriteRecipesTestTags.LOADING).assertIsDisplayed()
    }

    @Test
    fun `a failed first load offers a retry`() {
        val calls = render(FavoriteRecipesUiState(loadError = FavoriteError.UNKNOWN))

        compose.onNodeWithText(str(R.string.error_favorites_load_unknown)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.meal_plans_retry)).performClick()

        assertEquals(1, calls.retries)
    }

    @Test
    fun `no favorites says so and explains how to add one`() {
        render(loaded())

        compose.onNodeWithText(str(R.string.favorites_empty_title)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.favorites_empty_description)).assertIsDisplayed()
    }

    @Test
    fun `favorites are listed with their numbers and every one has a filled heart`() {
        render(loaded(recipe("1", "Soup", calories = 120), recipe("2", "Stew")))

        compose.onNodeWithText("Soup").assertIsDisplayed()
        compose.onNodeWithText("Stew").assertIsDisplayed()
        compose.onNodeWithText("120 kcal").assertIsDisplayed()
        assertEquals(2, compose.onAllNodesWithTag(FavoriteTestTags.TOGGLE).fetchSemanticsNodes().size)
        assertEquals(
            2,
            compose.onAllNodesWithContentDescription(str(R.string.favorite_remove)).fetchSemanticsNodes().size,
        )
    }

    @Test
    fun `tapping a favorite opens that recipe`() {
        val calls = render(loaded(recipe("r7", "Lentil soup")))

        compose.onNodeWithText("Lentil soup").performClick()

        assertEquals(listOf("r7"), calls.opened)
    }

    @Test
    fun `tapping the heart asks to remove that favorite and does not open it`() {
        val calls = render(loaded(recipe("1", "Soup"), recipe("2", "Stew")))

        compose.onAllNodesWithTag(FavoriteTestTags.TOGGLE).onFirst().performClick()

        assertEquals(listOf("1"), calls.toggled)
        assertEquals(emptyList<String>(), calls.opened)
    }

    @Test
    fun `a heart is disabled while its change is being sent`() {
        render(
            FavoriteRecipesUiState(
                recipes = listOf(recipe("1", "Soup")),
                hasLoaded = true,
                pendingIds = setOf("1"),
            ),
        )

        compose.onNodeWithTag(FavoriteTestTags.TOGGLE).assertIsNotEnabled()
    }

    @Test
    fun `offline the saved copy is shown with a note saying so`() {
        render(loaded(recipe("1", "Soup"), offline = true))

        compose.onNodeWithTag(FavoriteRecipesTestTags.OFFLINE_NOTE)
            .assertIsDisplayed()
            .assert(hasLiveRegion())
        compose.onNodeWithText(str(R.string.favorites_offline)).assertIsDisplayed()
        compose.onNodeWithText("Soup").assertIsDisplayed()
    }

    @Test
    fun `online there is no offline note`() {
        render(loaded(recipe("1", "Soup")))

        compose.onNodeWithTag(FavoriteRecipesTestTags.OFFLINE_NOTE).assertDoesNotExist()
    }

    @Test
    fun `an undone change is announced politely`() {
        render(
            FavoriteRecipesUiState(
                recipes = listOf(recipe("1", "Soup")),
                hasLoaded = true,
                changeError = FavoriteError.NETWORK,
            ),
        )

        compose.onNodeWithTag(FavoriteTestTags.ERROR_BANNER)
            .assertIsDisplayed()
            .assert(hasLiveRegion())
        compose.onNodeWithText(str(R.string.error_favorite_change_network)).assertIsDisplayed()
    }

    @Test
    fun `a refresh that failed keeps the list that is already shown`() {
        render(
            FavoriteRecipesUiState(
                recipes = listOf(recipe("1", "Soup")),
                hasLoaded = true,
                loadError = FavoriteError.UNKNOWN,
            ),
        )

        compose.onNodeWithText("Soup").assertIsDisplayed()
    }

    @Test
    fun `back is reported`() {
        val calls = render(loaded())

        compose.onNodeWithContentDescription(str(R.string.cd_meal_plans_back)).performClick()

        assertEquals(1, calls.backed)
    }
}
