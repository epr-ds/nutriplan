package com.nutriplan.android.recipes

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
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
import com.nutriplan.android.screen.recipes.RecipeSearchScreenContent
import com.nutriplan.android.screen.recipes.RecipeSearchTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.recipes.RecipeListError
import com.nutriplan.shared.recipes.RecipeSearchUiState
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onFirst
import com.nutriplan.android.screen.recipes.FavoriteTestTags
import com.nutriplan.shared.recipes.FavoriteError
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * DPL-601: the recipe search shows the filters and the results with their key numbers, and every
 * state (loading, empty, error, more pages) is reachable and accessible. Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
// A tall viewport so every lazily composed list item is on screen.
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2000dp", application = TestApplication::class)
class RecipeSearchScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private fun recipe(
        id: String,
        name: String,
        prep: Int? = null,
        cook: Int? = null,
        calories: Int? = null,
        protein: Double? = null,
        imageUrl: String? = null,
    ) = Recipe(
        id = id,
        name = name,
        prepTime = prep,
        cookTime = cook,
        imageUrl = imageUrl,
        nutritionalInfo = if (calories != null || protein != null) {
            NutritionalInfo(calories = calories, protein = protein)
        } else {
            null
        },
    )

    private fun render(
        state: RecipeSearchUiState,
        onIngredientsChange: (String) -> Unit = {},
        onDietTypeChange: (String?) -> Unit = {},
        onMaxCaloriesChange: (String) -> Unit = {},
        onMinProteinChange: (String) -> Unit = {},
        onSearch: () -> Unit = {},
        onClearFilters: () -> Unit = {},
        onLoadMore: () -> Unit = {},
        onRecipeClick: (String) -> Unit = {},
        onBack: () -> Unit = {},
        isPicking: Boolean = false,
    ) {
        compose.setContent {
            NutriPlanTheme {
                RecipeSearchScreenContent(
                    state = state,
                    onIngredientsChange = onIngredientsChange,
                    onDietTypeChange = onDietTypeChange,
                    onMaxCaloriesChange = onMaxCaloriesChange,
                    onMinProteinChange = onMinProteinChange,
                    onSearch = onSearch,
                    onClearFilters = onClearFilters,
                    onLoadMore = onLoadMore,
                    onRecipeClick = onRecipeClick,
                    onBack = onBack,
                    isPicking = isPicking,
                )
            }
        }
    }

    @Test
    fun `when choosing a recipe for a plan the title says so`() {
        render(RecipeSearchUiState(), isPicking = true)

        compose.onNode(isHeading() and hasText(str(R.string.recipes_pick_title))).assertIsDisplayed()
    }

    @Test
    fun `the title is a heading and the filters are shown`() {
        render(RecipeSearchUiState())

        compose.onNode(isHeading() and hasText(str(R.string.recipes_title))).assertIsDisplayed()
        compose.onNodeWithTag(RecipeSearchTestTags.INGREDIENTS).assertIsDisplayed()
        compose.onNodeWithTag(RecipeSearchTestTags.MAX_CALORIES).assertIsDisplayed()
        compose.onNodeWithTag(RecipeSearchTestTags.MIN_PROTEIN).assertIsDisplayed()
        compose.onNodeWithTag(RecipeSearchTestTags.SEARCH).assertIsDisplayed()
        // One chip for "any" plus one per diet type.
        assertEquals(6, compose.onAllNodesWithTag(RecipeSearchTestTags.DIET_CHIP).fetchSemanticsNodes().size)
    }

    @Test
    fun `typing in the filters reports the text`() {
        var ingredients = ""
        var calories = ""
        var protein = ""
        compose.setContent {
            // Hosted with real state, as in the app: a controlled field only shows what the state holds.
            var state by remember { mutableStateOf(RecipeSearchUiState()) }
            NutriPlanTheme {
                RecipeSearchScreenContent(
                    state = state,
                    onIngredientsChange = { state = state.copy(ingredients = it); ingredients = it },
                    onDietTypeChange = {},
                    onMaxCaloriesChange = { state = state.copy(maxCalories = it); calories = it },
                    onMinProteinChange = { state = state.copy(minProtein = it); protein = it },
                    onSearch = {},
                    onClearFilters = {},
                    onLoadMore = {},
                    onRecipeClick = {},
                    onBack = {},
                )
            }
        }

        compose.onNodeWithTag(RecipeSearchTestTags.INGREDIENTS).performTextInput("chicken")
        compose.onNodeWithTag(RecipeSearchTestTags.MAX_CALORIES).performTextInput("600")
        compose.onNodeWithTag(RecipeSearchTestTags.MIN_PROTEIN).performTextInput("25")

        compose.onNodeWithTag(RecipeSearchTestTags.INGREDIENTS).assert(hasText("chicken"))
        assertEquals("chicken", ingredients)
        assertEquals("600", calories)
        assertEquals("25", protein)
    }

    @Test
    fun `the chosen diet is selected and choosing one reports it`() {
        var chosen: String? = "unset"
        render(RecipeSearchUiState(dietType = "vegan"), onDietTypeChange = { chosen = it })

        compose.onNodeWithText(str(R.string.diet_vegan)).assertIsSelected()
        compose.onNodeWithText(str(R.string.diet_keto)).performClick()
        assertEquals("keto", chosen)
        compose.onNodeWithText(str(R.string.recipes_filter_diet_any)).performClick()
        assertEquals(null, chosen)
    }

    @Test
    fun `search reports a tap, and is disabled while loading`() {
        var searches = 0
        render(RecipeSearchUiState(), onSearch = { searches++ })
        compose.onNodeWithTag(RecipeSearchTestTags.SEARCH).assertIsEnabled().performClick()
        assertEquals(1, searches)
    }

    @Test
    fun `search is disabled and a labelled spinner is shown while loading`() {
        render(RecipeSearchUiState(isLoading = true))

        compose.onNodeWithTag(RecipeSearchTestTags.SEARCH).assertIsNotEnabled()
        compose.onNodeWithTag(RecipeSearchTestTags.LOADING).assertIsDisplayed()
        compose.onNodeWithContentDescription(str(R.string.cd_recipes_loading)).assertExists()
    }

    @Test
    fun `clear filters appears only when a filter is set`() {
        var cleared = 0
        render(RecipeSearchUiState(dietType = "keto"), onClearFilters = { cleared++ })

        compose.onNodeWithTag(RecipeSearchTestTags.CLEAR).performClick()
        assertEquals(1, cleared)
    }

    @Test
    fun `clear filters is hidden without filters`() {
        render(RecipeSearchUiState())

        compose.onNodeWithTag(RecipeSearchTestTags.CLEAR).assertDoesNotExist()
    }

    @Test
    fun `results show time, calories and protein, and only what the recipe has`() {
        render(
            RecipeSearchUiState(
                recipes = listOf(
                    recipe("1", "Chicken bowl", prep = 10, cook = 20, calories = 520, protein = 32.5),
                    recipe("2", "Plain rice"),
                ),
                hasSearched = true,
            ),
        )

        compose.onNodeWithText("Chicken bowl").assertIsDisplayed()
        compose.onNodeWithText("30 min · 520 kcal · 32.5 g protein").assertIsDisplayed()
        compose.onNodeWithText("Plain rice").assertIsDisplayed()
        assertEquals(2, compose.onAllNodesWithTag(RecipeSearchTestTags.RECIPE_CARD).fetchSemanticsNodes().size)
    }

    @Test
    fun `a recipe with an image still renders (the image is decorative)`() {
        render(
            RecipeSearchUiState(
                recipes = listOf(recipe("1", "Chicken bowl", imageUrl = "https://example.test/bowl.jpg")),
                hasSearched = true,
            ),
        )

        compose.onNodeWithText("Chicken bowl").assertIsDisplayed()
    }

    @Test
    fun `tapping a result opens that recipe`() {
        var opened: String? = null
        render(
            RecipeSearchUiState(recipes = listOf(recipe("r7", "Lentil soup")), hasSearched = true),
            onRecipeClick = { opened = it },
        )

        compose.onNodeWithText("Lentil soup").performClick()

        assertEquals("r7", opened)
    }

    @Test
    fun `an empty result says so`() {
        render(RecipeSearchUiState(hasSearched = true))

        compose.onNodeWithText(str(R.string.recipes_empty_title)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.recipes_empty_description)).assertIsDisplayed()
    }

    @Test
    fun `nothing says empty before the first search`() {
        render(RecipeSearchUiState())

        compose.onNodeWithText(str(R.string.recipes_empty_title)).assertDoesNotExist()
    }

    @Test
    fun `an error is announced politely`() {
        render(RecipeSearchUiState(hasSearched = true, error = RecipeListError.NETWORK))

        compose.onNodeWithTag(RecipeSearchTestTags.ERROR_BANNER)
            .assertIsDisplayed()
            .assert(hasLiveRegion())
        compose.onNodeWithText(str(R.string.error_recipes_network)).assertIsDisplayed()
        // An error is not an empty result.
        compose.onNodeWithText(str(R.string.recipes_empty_title)).assertDoesNotExist()
    }

    @Test
    fun `show more appears when another page may exist and reports a tap`() {
        var more = 0
        render(
            RecipeSearchUiState(recipes = listOf(recipe("1", "A")), hasMore = true, hasSearched = true),
            onLoadMore = { more++ },
        )

        compose.onNodeWithTag(RecipeSearchTestTags.LOAD_MORE).performClick()

        assertEquals(1, more)
    }

    @Test
    fun `show more is replaced by a labelled spinner while the next page loads`() {
        render(
            RecipeSearchUiState(
                recipes = listOf(recipe("1", "A")),
                hasMore = true,
                isLoadingMore = true,
                hasSearched = true,
            ),
        )

        compose.onNodeWithTag(RecipeSearchTestTags.LOAD_MORE).assertDoesNotExist()
        compose.onNodeWithContentDescription(str(R.string.cd_recipes_loading_more)).assertExists()
    }

    @Test
    fun `back is reported`() {
        var back = 0
        render(RecipeSearchUiState(), onBack = { back++ })

        compose.onNodeWithContentDescription(str(R.string.cd_meal_plans_back)).performClick()

        assertEquals(1, back)
    }

    @Test
    fun `the diet chips use the localized names`() {
        render(RecipeSearchUiState())

        compose.onNodeWithText(str(R.string.diet_omnivore)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.diet_vegetarian)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.diet_paleo)).assertIsDisplayed()
    }

    // --- favorites (DPL-607) ---

    @Test
    fun `no hearts and no favorites entry by default`() {
        render(RecipeSearchUiState(recipes = listOf(recipe("1", "Soup")), hasSearched = true))

        assertEquals(0, compose.onAllNodesWithTag(FavoriteTestTags.TOGGLE).fetchSemanticsNodes().size)
        compose.onNodeWithTag(RecipeSearchTestTags.OPEN_FAVORITES).assertDoesNotExist()
    }

    private fun renderWithFavorites(
        state: RecipeSearchUiState,
        favoriteIds: Set<String> = emptySet(),
        pending: Set<String> = emptySet(),
        error: FavoriteError? = null,
        toggled: MutableList<String> = mutableListOf(),
        onOpenFavorites: (() -> Unit)? = null,
    ) {
        compose.setContent {
            NutriPlanTheme {
                RecipeSearchScreenContent(
                    state = state,
                    onIngredientsChange = {},
                    onDietTypeChange = {},
                    onMaxCaloriesChange = {},
                    onMinProteinChange = {},
                    onSearch = {},
                    onClearFilters = {},
                    onLoadMore = {},
                    onRecipeClick = {},
                    onBack = {},
                    favoriteIds = favoriteIds,
                    pendingFavoriteIds = pending,
                    favoriteError = error,
                    onToggleFavorite = { toggled += it.id },
                    onOpenFavorites = onOpenFavorites,
                )
            }
        }
    }

    private val twoResults = RecipeSearchUiState(
        recipes = listOf(recipe("1", "Soup"), recipe("2", "Stew")),
        hasSearched = true,
    )

    @Test
    fun `every result has a heart that says what a tap does`() {
        renderWithFavorites(twoResults, favoriteIds = setOf("2"))

        assertEquals(2, compose.onAllNodesWithTag(FavoriteTestTags.TOGGLE).fetchSemanticsNodes().size)
        assertEquals(1, compose.onAllNodesWithContentDescription(str(R.string.favorite_add)).fetchSemanticsNodes().size)
        assertEquals(1, compose.onAllNodesWithContentDescription(str(R.string.favorite_remove)).fetchSemanticsNodes().size)
    }

    @Test
    fun `tapping a heart toggles that recipe without opening it`() {
        val toggled = mutableListOf<String>()
        var opened = 0
        compose.setContent {
            NutriPlanTheme {
                RecipeSearchScreenContent(
                    state = twoResults,
                    onIngredientsChange = {},
                    onDietTypeChange = {},
                    onMaxCaloriesChange = {},
                    onMinProteinChange = {},
                    onSearch = {},
                    onClearFilters = {},
                    onLoadMore = {},
                    onRecipeClick = { opened++ },
                    onBack = {},
                    onToggleFavorite = { toggled += it.id },
                )
            }
        }

        compose.onAllNodesWithTag(FavoriteTestTags.TOGGLE).onFirst().performClick()

        assertEquals(listOf("1"), toggled)
        assertEquals(0, opened)
    }

    @Test
    fun `a heart is disabled while its change is being sent`() {
        renderWithFavorites(twoResults, pending = setOf("1"))

        compose.onAllNodesWithTag(FavoriteTestTags.TOGGLE).onFirst().assertIsNotEnabled()
    }

    @Test
    fun `an undone change is announced politely`() {
        renderWithFavorites(twoResults, error = FavoriteError.NETWORK)

        compose.onNodeWithTag(FavoriteTestTags.ERROR_BANNER).assertIsDisplayed().assert(hasLiveRegion())
        compose.onNodeWithText(str(R.string.error_favorite_change_network)).assertIsDisplayed()
    }

    @Test
    fun `the favorites entry opens the favorites list`() {
        var opened = 0
        renderWithFavorites(twoResults, onOpenFavorites = { opened++ })

        compose.onNodeWithTag(RecipeSearchTestTags.OPEN_FAVORITES).performClick()

        assertEquals(1, opened)
        compose.onNodeWithContentDescription(str(R.string.cd_favorites_open)).assertExists()
    }}
