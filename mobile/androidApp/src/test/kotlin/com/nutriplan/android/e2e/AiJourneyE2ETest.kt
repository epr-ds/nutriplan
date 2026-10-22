package com.nutriplan.android.e2e

import android.content.Context
import android.graphics.Bitmap
import androidx.annotation.StringRes
import androidx.compose.runtime.remember
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.navigation.compose.rememberNavController
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.MainNavigationScreens
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.navigation.AppNavigationGraph
import com.nutriplan.android.screen.ai.AiRecommendationsTestTags
import com.nutriplan.android.screen.plans.AddMealTestTags
import com.nutriplan.android.screen.recipes.RecipeSearchTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.local.DatabaseDriverFactory
import com.nutriplan.shared.data.local.StoredTokens
import com.nutriplan.shared.data.local.TokenStorage
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.DietaryPreferences
import com.nutriplan.shared.data.model.UserProfile
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.data.repository.DietaryRepositoryImpl
import com.nutriplan.shared.di.cacheModule
import com.nutriplan.shared.di.dataModule
import com.nutriplan.shared.di.planningModule
import com.nutriplan.shared.di.recipesModule
import com.nutriplan.shared.di.sessionModule
import com.nutriplan.shared.navigation.Route
import com.nutriplan.shared.onboarding.OnboardingDraftStorage
import com.nutriplan.shared.session.SessionManager
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
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
 * AIA-705: headless AI-journey E2E (Android): get recommendations → add one to a plan → the added
 * meal respects the user's allergies and calorie target.
 *
 * Drives the **real app navigation and screens** (AI recommendations → plan picker → add-meal form →
 * back on the recommendations) through the real shared view-models, repositories and on-device
 * cache, for a signed-in user allergic to peanuts. The AI Advisor stand-in's "model" proposes a
 * peanut dish first and only the service's allergy post-filter removes it, so a safe meal proves
 * the app sent the user's allergies. Runs on the JVM via Robolectric (no emulator) in the
 * `android-ai-e2e` CI job.
 *
 * On failure it leaves a screenshot of the screen and a step-by-step trace (with every request the
 * app made) in `build/reports/e2e/`, which CI uploads with the JUnit report. The same journey runs
 * through the shared layer on iOS in `AiJourneyTest` (shared module).
 */
@RunWith(AndroidJUnit4::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
// Tall, so every recommendation and its button are composed without scrolling the lazy list.
@Config(sdk = [34], qualifiers = "en-rUS-w411dp-h1800dp", application = TestApplication::class)
class AiJourneyE2ETest {

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

    private val peanutNoodles = FakeDietaryBackend.CatalogRecipe(
        "peanut-noodles", "Peanut Noodles", calories = 620, protein = 20.0, carbs = 70.0, fat = 28.0, sugar = 9.0,
        ingredients = listOf("rice noodles", "peanut butter", "lime"),
    )
    private val lentilCurry = FakeDietaryBackend.CatalogRecipe(
        "lentil-curry", "Lentil Curry", calories = 480, protein = 24.0, carbs = 62.0, fat = 12.0, sugar = 8.0,
        ingredients = listOf("red lentils", "coconut milk", "spinach"),
        dietaryTypes = listOf("vegan", "vegetarian"),
    )
    private val ai = FakeAiAdvisor(proposals = listOf(peanutNoodles, lentilCurry))
    private val backend = FakeDietaryBackend(listOf(peanutNoodles, lentilCurry), ai)

    /** The signed-in user: vegan, allergic to peanuts, 2,000 kcal a day. */
    private val preferences = DietaryPreferences(
        dietType = "vegan",
        allergies = listOf("Peanuts"),
        dailyCalorieTarget = 2000,
    )

    /** What the journey did, step by step, for the failure trace. */
    private val trace = mutableListOf<String>()

    private lateinit var planId: String

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
                    single<TokenStorage> { AiJourneyTokenStorage() }
                    single<OnboardingDraftStorage> { AiJourneyNoDraftStorage() }
                },
                cacheModule(DatabaseDriverFactory(context)),
            )
        }
        HttpClientProvider.create(backend.engine, GlobalContext.get().get<AuthRepository>())
        GlobalContext.get().get<SessionManager>().onAuthenticated(
            UserProfile(id = "u1", email = "ana@example.com", name = "Ana", dietaryPreferences = preferences),
        )
        // The user already has a plan for the week to add recommendations to.
        planId = runBlocking {
            DietaryRepositoryImpl().createMealPlan(
                CreateMealPlanRequest(
                    name = "Week 40",
                    startDate = "2026-10-01",
                    endDate = "2026-10-07",
                    dailyCalorieTarget = 2000,
                ),
            ).id
        }
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
    fun recommend_add_to_a_plan_and_the_meal_respects_the_allergies_and_the_target() {
        compose.setContent {
            NutriPlanTheme {
                val navController = rememberNavController()
                AppNavigationGraph(
                    navController = navController,
                    startDestination = Route.AiRecommendations,
                    screens = remember(navController) { MainNavigationScreens(navController) },
                )
            }
        }

        step("the recommendations open, without the dish the user is allergic to") {
            waitFor(hasTestTag(RecipeSearchTestTags.RECIPE_CARD))
            compose.onNodeWithText("Lentil Curry").assertExists()
            compose.onNodeWithText("Peanut Noodles").assertDoesNotExist()
        }

        step("ask again for dinner") {
            compose.onNodeWithText(str(R.string.meal_type_dinner)).performClick()
            compose.onNodeWithTag(AiRecommendationsTestTags.SUBMIT).performClick()
            compose.waitUntil(10_000) { ai.recommendationRequests.size == 2 }
            waitFor(hasTestTag(RecipeSearchTestTags.RECIPE_CARD))
        }

        step("add Lentil Curry to a plan") {
            compose.onNodeWithContentDescription(str(R.string.cd_ai_recommendations_add_to_plan, "Lentil Curry"))
                .performClick()
        }

        step("choose the week's plan") {
            waitFor(hasText("Week 40"))
            compose.onNodeWithText("Week 40").performClick()
        }

        step("the add-meal form already has dinner chosen; add it") {
            waitFor(hasTestTag(AddMealTestTags.RECIPE))
            compose.onNode(hasTestTag(AddMealTestTags.MEAL_TYPE_CHIP) and hasText(str(R.string.meal_type_dinner)))
                .assertIsSelected()
            compose.onNodeWithTag(AddMealTestTags.SUBMIT).performScrollTo().performClick()
        }

        step("back on the recommendations, the add is confirmed") {
            waitFor(hasTestTag(AiRecommendationsTestTags.ADDED_NOTICE))
        }

        step("the app sent the user's allergies, diet and target with the dinner request") {
            val sent = ai.recommendationRequests.last()
            val sentPreferences = sent["dietaryPreferences"]!!.jsonObject
            assertEquals(listOf("Peanuts"), sentPreferences["allergies"]!!.jsonArray.map { it.jsonPrimitive.content })
            assertEquals("vegan", sentPreferences["dietType"]!!.jsonPrimitive.content)
            assertEquals("dinner", sent["mealType"]!!.jsonPrimitive.content)
            assertEquals("2000", sent["calorieTarget"]!!.jsonPrimitive.content)
        }

        step("the meal in the plan is safe for the user and fits the target") {
            val added = backend.mealRecipes(planId).single()
            assertEquals("lentil-curry", added.id)
            preferences.allergies.orEmpty().forEach { allergy ->
                assertFalse("${added.name} contains $allergy: ${added.ingredients}", added.contains(allergy))
            }
            assertTrue("${added.name} is not vegan", "vegan" in added.dietaryTypes)

            val plan = runBlocking { DietaryRepositoryImpl().getMealPlan(planId) }
            assertEquals(listOf("dinner"), plan.meals.map { it.mealType })
            val calories = plan.nutritionalSummary!!.progress.calories
            assertEquals(2000.0, calories.target)
            assertNotEquals("the plan goes over the calorie target: $calories", "over", calories.status)
        }
    }
}

/** In-memory [TokenStorage] so the E2E does not touch the Android Keystore. */
private class AiJourneyTokenStorage : TokenStorage {
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
private class AiJourneyNoDraftStorage : OnboardingDraftStorage {
    override fun loadDraft(): String? = null
    override fun saveDraft(draft: String) = Unit
    override fun clearDraft() = Unit
}
