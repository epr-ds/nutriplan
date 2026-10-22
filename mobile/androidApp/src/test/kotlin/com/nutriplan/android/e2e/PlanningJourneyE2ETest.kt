package com.nutriplan.android.e2e

import android.content.Context
import android.graphics.Bitmap
import androidx.annotation.StringRes
import androidx.compose.runtime.remember
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTextReplacement
import androidx.navigation.compose.rememberNavController
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.MainNavigationScreens
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.navigation.AppNavigationGraph
import com.nutriplan.android.screen.plans.AddMealTestTags
import com.nutriplan.android.screen.plans.MealPlanFormTestTags
import com.nutriplan.android.screen.plans.MealPlanListTestTags
import com.nutriplan.android.screen.plans.NutritionSummaryTestTags
import com.nutriplan.android.screen.recipes.RecipeSearchTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.local.DatabaseDriverFactory
import com.nutriplan.shared.data.local.StoredTokens
import com.nutriplan.shared.data.local.TokenStorage
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.di.cacheModule
import com.nutriplan.shared.di.dataModule
import com.nutriplan.shared.di.planningModule
import com.nutriplan.shared.di.recipesModule
import com.nutriplan.shared.di.sessionModule
import com.nutriplan.shared.navigation.Route
import com.nutriplan.shared.onboarding.OnboardingDraftStorage
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TestWatcher
import org.junit.runner.Description
import org.junit.runner.RunWith
import org.koin.core.context.GlobalContext
import org.koin.core.context.startKoin
import org.koin.core.context.stopKoin
import org.koin.dsl.module
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File

/**
 * DPL-704: headless planning-journey E2E (Android): create a plan → add a meal → see the nutrition.
 *
 * Drives the **real app navigation and screens** (plan list → create-plan form → plan detail →
 * recipe picker → add-meal form → back on the plan) through the real shared view-models,
 * repositories and on-device cache, against a stateful Dietary backend stand-in that computes the
 * plan's nutrition like the service. It asserts the nutrition card the user sees after adding the
 * meal. Runs on the JVM via Robolectric (no emulator) in the `android-planning-e2e` CI job.
 *
 * On failure it leaves a screenshot of the screen and a step-by-step trace (with every request the
 * app made) in `build/reports/e2e/`, which CI uploads with the JUnit report. The same journey runs
 * through the shared layer on iOS in `PlanningJourneyTest` (shared module).
 */
@RunWith(AndroidJUnit4::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "en-rUS-w411dp-h891dp", application = TestApplication::class)
class PlanningJourneyE2ETest {

    @get:Rule(order = 0)
    val compose = createComposeRule()

    /** Inner to the compose rule, so the screen is still there to be captured when a step fails. */
    @get:Rule(order = 1)
    val artifacts = object : TestWatcher() {
        override fun failed(e: Throwable, description: Description) {
            val dir = File("build/reports/e2e").apply { mkdirs() }
            val name = description.methodName
            File(dir, "$name-trace.txt").writeText(
                (trace + listOf("", "Requests:") + backend.requests + listOf("", "Failure: $e")).joinToString("\n"),
            )
            runCatching {
                File(dir, "$name.png").outputStream().use {
                    compose.onRoot().captureToImage().asAndroidBitmap().compress(Bitmap.CompressFormat.PNG, 100, it)
                }
            }
        }
    }

    private val backend = FakeDietaryBackend(
        listOf(
            FakeDietaryBackend.CatalogRecipe("oats", "Overnight Oats", calories = 350, protein = 12.0, carbs = 60.0, fat = 8.0, sugar = 10.0),
            FakeDietaryBackend.CatalogRecipe("salad", "Chicken Salad", calories = 280, protein = 18.0, carbs = 10.0, fat = 15.0, sugar = 4.0),
        ),
    )

    /** What the journey did, step by step, for the failure trace. */
    private val trace = mutableListOf<String>()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    @Before
    fun setUp() {
        startKoin {
            modules(
                dataModule,
                sessionModule,
                planningModule,
                recipesModule,
                module {
                    single<TokenStorage> { PlanningTokenStorage() }
                    single<OnboardingDraftStorage> { NoDraftStorage() }
                },
                cacheModule(DatabaseDriverFactory(context)),
            )
        }
        HttpClientProvider.create(backend.engine, GlobalContext.get().get<AuthRepository>())
    }

    @After
    fun tearDown() {
        HttpClientProvider.reset()
        stopKoin()
        ApiConfig.reset()
    }

    private fun step(name: String, block: () -> Unit) {
        trace += name
        block()
    }

    private fun waitFor(matcher: SemanticsMatcher, timeoutMillis: Long = 10_000) {
        compose.waitUntil(timeoutMillis) { compose.onAllNodes(matcher).fetchSemanticsNodes().isNotEmpty() }
    }

    @Test
    fun create_a_plan_add_a_meal_and_see_the_nutrition() {
        compose.setContent {
            NutriPlanTheme {
                val navController = rememberNavController()
                AppNavigationGraph(
                    navController = navController,
                    startDestination = Route.MealPlanList,
                    screens = remember(navController) { MainNavigationScreens(navController) },
                )
            }
        }

        step("open the create-plan form from the plan list") {
            waitFor(hasTestTag(MealPlanListTestTags.CREATE))
            compose.onNodeWithTag(MealPlanListTestTags.CREATE).performClick()
        }

        step("fill in the plan (a week from today, 2,000 kcal a day) and create it") {
            waitFor(hasTestTag(MealPlanFormTestTags.NAME))
            compose.onNodeWithTag(MealPlanFormTestTags.NAME).performTextInput("Week 40")
            compose.onNodeWithTag(MealPlanFormTestTags.CALORIES).performTextInput("2000")
            compose.onNodeWithTag(MealPlanFormTestTags.SUBMIT).performScrollTo().performClick()
        }

        step("the new, empty plan opens; add a meal") {
            waitFor(hasText(str(R.string.plan_detail_add_meal)))
            compose.onNodeWithText(str(R.string.plan_detail_add_meal)).performClick()
        }

        step("choose Overnight Oats in the recipe picker") {
            waitFor(hasTestTag(RecipeSearchTestTags.RECIPE_CARD))
            compose.onNodeWithText("Overnight Oats").performClick()
        }

        step("add it as breakfast, 2 servings") {
            waitFor(hasTestTag(AddMealTestTags.RECIPE))
            compose.onNodeWithText(str(R.string.meal_type_breakfast)).performClick()
            compose.onNodeWithTag(AddMealTestTags.SERVINGS).performTextReplacement("2")
            compose.onNodeWithTag(AddMealTestTags.SUBMIT).performScrollTo().performClick()
        }

        step("back on the plan, the nutrition card shows the meal against the target") {
            waitFor(hasTestTag(NutritionSummaryTestTags.CARD))
            // 2 x 350 kcal over the plan's 7 days = 100 kcal a day, 5% of 2,000.
            compose.onNodeWithText(str(R.string.nutrition_kcal_of_target, "100", "2,000")).assertExists()
            compose.onNodeWithText(str(R.string.nutrition_percent, 5)).assertExists()
            assertTrue(
                "expected the calories to be under target",
                compose.onAllNodesWithTag(NutritionSummaryTestTags.ROW).fetchSemanticsNodes().isNotEmpty(),
            )
            compose.onNodeWithText(str(R.string.nutrition_status_under), useUnmergedTree = true).assertExists()
        }

        step("the app made the expected calls") {
            assertTrue("a plan was created: ${backend.requests}", "POST /meal-plans" in backend.requests)
            assertTrue(
                "a meal was added: ${backend.requests}",
                backend.requests.any { it.startsWith("POST /meal-plans/") && it.endsWith("/meals") },
            )
        }
    }
}

/** In-memory [TokenStorage] so the E2E does not touch the Android Keystore. */
private class PlanningTokenStorage : TokenStorage {
    private var tokens: StoredTokens? = null
    override fun load(): StoredTokens? = tokens
    override fun save(accessToken: String, refreshToken: String) {
        tokens = StoredTokens(accessToken, refreshToken)
    }
    override fun clear() {
        tokens = null
    }
}

/** No onboarding draft: the journey starts signed in. */
private class NoDraftStorage : OnboardingDraftStorage {
    override fun loadDraft(): String? = null
    override fun saveDraft(draft: String) = Unit
    override fun clearDraft() = Unit
}
