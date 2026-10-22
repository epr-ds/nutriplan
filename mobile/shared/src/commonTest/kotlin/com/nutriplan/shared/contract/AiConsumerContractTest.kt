package com.nutriplan.shared.contract

import com.nutriplan.shared.ai.AiAdvisor
import com.nutriplan.shared.ai.AiResult
import com.nutriplan.shared.data.model.AiDietaryPreferences
import com.nutriplan.shared.data.model.AiRecommendationRequest
import com.nutriplan.shared.data.model.AnalyzeMealRequest
import com.nutriplan.shared.data.model.DietaryMacroTargets
import com.nutriplan.shared.data.model.DietaryPreferences
import com.nutriplan.shared.data.model.OptimizePlanRequest
import com.nutriplan.shared.data.model.RecipeIngredient
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.AiRepositoryImpl
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Consumer contract tests for the KMP AI client (AIA-703).
 *
 * The real client the app ships ([AiRepositoryImpl]) and its use cases ([AiAdvisor]) are pointed at
 * [SpecDerivedAiMock]. Every call must hit a documented AI operation with a schema-shaped body (no
 * undocumented or null fields, documented enum values, the nested preferences included) and the
 * client must read the spec-shaped reply. A drifted client fails here; the mock itself is kept equal
 * to the OpenAPI document by `scripts/check_mobile_ai_contract.py`.
 */
class AiConsumerContractTest {

    private val mock = SpecDerivedAiMock()
    private lateinit var ai: AiRepositoryImpl

    @BeforeTest
    fun setUp() {
        HttpClientProvider.create(mock.engine, authRepository = null)
        ai = AiRepositoryImpl()
    }

    @AfterTest
    fun tearDown() = HttpClientProvider.reset()

    private fun assertNoViolations() =
        assertTrue(mock.violations.isEmpty(), "contract violations: ${mock.violations}")

    // --- the repository ---

    @Test
    fun `a minimal recommendation request conforms and the reply is read in full`() = runTest {
        val result = ai.recommendations(AiRecommendationRequest(context = "meal_plan"))

        assertEquals(listOf("POST /ai/recommendations"), mock.calls)
        val recipe = result.recommendations.single()
        assertEquals("Lentil Soup", recipe.name)
        assertEquals(20, recipe.cookTime)
        assertEquals(320, recipe.nutritionalInfo?.calories)
        assertEquals(87.5, result.nutritionalAlignment?.score)
        assertEquals("This is not medical advice.", result.disclaimer)
        assertEquals("model", result.source)
        assertFalse(result.isCuratedFallback)
        assertNoViolations()
    }

    @Test
    fun `a full recommendation request with nested preferences conforms`() = runTest {
        ai.recommendations(
            AiRecommendationRequest(
                context = "ingredient_based",
                dietaryPreferences = AiDietaryPreferences(
                    dietType = "mediterranean",
                    allergies = listOf("peanuts"),
                    dailyCalorieTarget = 1800,
                    macroTargets = DietaryMacroTargets(proteinGrams = 120, carbsGrams = 200, fatGrams = 60, sugarGrams = 30),
                    excludedIngredients = listOf("tofu"),
                    cuisinePreferences = listOf("mexican"),
                ),
                availableIngredients = listOf("rice", "beans"),
                mealType = "lunch",
                calorieTarget = 600,
                previousMeals = listOf("Oats"),
                constraints = listOf("under 30 minutes"),
                language = "en",
            ),
        )

        assertNoViolations()
    }

    @Test
    fun `analyzing a meal conforms with and without ingredients`() = runTest {
        val analysis = ai.analyzeMeal(AnalyzeMealRequest("Chicken with rice"))
        ai.analyzeMeal(
            AnalyzeMealRequest(
                "Bowl",
                ingredients = listOf(RecipeIngredient(name = "Rice", quantity = 100.0, unit = "g", calories = 130)),
            ),
        )

        assertEquals(540, analysis.nutritionalInfo?.calories)
        assertNull(analysis.nutritionalInfo?.sugar)
        assertEquals(72.0, analysis.alignment?.score)
        assertEquals(listOf("High in sodium"), analysis.warnings)
        assertEquals("Estimates only, not medical advice.", analysis.disclaimer)
        assertNoViolations()
    }

    @Test
    fun `optimizing a plan conforms for every goal and reads the draft plan`() = runTest {
        ai.optimizePlan(OptimizePlanRequest("p1"))
        AiAdvisor.GOALS.forEach { goal -> ai.optimizePlan(OptimizePlanRequest("p1", goal = goal)) }

        val plan = ai.optimizePlan(OptimizePlanRequest("p1", goal = "balance_macros"))
        assertEquals("draft", plan.status)
        assertEquals(1.5, plan.meals.single().servings)
        assertNull(plan.meals.single().recipe)
        assertEquals(69, plan.nutritionalSummary?.dailyAverage?.calories)
        assertEquals(150, plan.nutritionalSummary?.targets?.protein)
        assertNoViolations()
    }

    // --- the use cases send conforming requests too ---

    @Test
    fun `the advisor's recommendation requests conform for every context`() = runTest {
        val advisor = AiAdvisor(ai) { "en" }
        val preferences = DietaryPreferences(
            dietType = "vegan",
            allergies = listOf("peanuts"),
            dailyCalorieTarget = 1800,
            macroTargets = DietaryMacroTargets(proteinGrams = 120),
            appetiteSatisfactionLevel = 3,
        )

        assertIs<AiResult.Success<*>>(advisor.recommend(preferences))
        assertIs<AiResult.Success<*>>(advisor.recommend(preferences, mealType = "dinner"))
        assertIs<AiResult.Success<*>>(advisor.recommend(null, availableIngredients = listOf("rice")))

        assertEquals(3, mock.calls.size)
        assertNoViolations()
    }

    @Test
    fun `the advisor's analysis and optimization requests conform`() = runTest {
        val advisor = AiAdvisor(ai)

        assertIs<AiResult.Success<*>>(advisor.analyzeMeal("Soup"))
        assertIs<AiResult.Success<*>>(advisor.optimizePlan("p1", goal = "reduce_calories"))
        assertNoViolations()
    }

    // --- the mock catches drift ---

    @Test
    fun `an undocumented operation is a violation`() = runTest {
        val response = HttpClientProvider.client.get("${AiContract.clientPrefix}/ai/meal-ideas")

        assertEquals(HttpStatusCode.BadRequest, response.status)
        assertTrue(mock.violations.any { it.contains("undocumented operation") })
    }

    @Test
    fun `an old field name is a violation`() = runTest {
        HttpClientProvider.client.post("${AiContract.clientPrefix}/ai/analyze-meal") {
            contentType(ContentType.Application.Json)
            setBody("""{"mealDescription":"Soup"}""")
        }

        assertTrue(mock.violations.any { it.contains("missing required") && it.contains("description") })
        assertTrue(mock.violations.any { it.contains("undocumented field") && it.contains("mealDescription") })
    }

    @Test
    fun `a value outside an enum is a violation`() = runTest {
        HttpClientProvider.client.post("${AiContract.clientPrefix}/ai/optimize-plan") {
            contentType(ContentType.Application.Json)
            setBody("""{"planId":"p1","goal":"lose_weight"}""")
        }

        assertTrue(mock.violations.any { it.contains("goal") && it.contains("lose_weight") })
    }

    @Test
    fun `a field sent as null instead of left out is a violation`() = runTest {
        HttpClientProvider.client.post("${AiContract.clientPrefix}/ai/recommendations") {
            contentType(ContentType.Application.Json)
            setBody("""{"context":"meal_plan","mealType":null}""")
        }

        assertTrue(mock.violations.any { it.contains("sent as null") && it.contains("mealType") })
    }

    @Test
    fun `an undocumented nested preference is a violation`() = runTest {
        HttpClientProvider.client.post("${AiContract.clientPrefix}/ai/recommendations") {
            contentType(ContentType.Application.Json)
            setBody("""{"context":"meal_plan","dietaryPreferences":{"appetiteSatisfactionLevel":3}}""")
        }

        assertTrue(mock.violations.any { it.contains("DietaryPreferencesRequest") && it.contains("appetiteSatisfactionLevel") })
    }

    @Test
    fun `every documented operation is exercised by this suite`() {
        assertEquals(
            setOf("POST /ai/recommendations", "POST /ai/analyze-meal", "POST /ai/optimize-plan"),
            AiContract.operations.map { "${it.method} ${it.path}" }.toSet(),
        )
    }
}
