package com.nutriplan.shared.ai

import com.nutriplan.shared.data.model.AiRecommendationRequest
import com.nutriplan.shared.data.model.AiRecommendations
import com.nutriplan.shared.data.model.AnalyzeMealRequest
import com.nutriplan.shared.data.model.DietaryMacroTargets
import com.nutriplan.shared.data.model.DietaryPreferences
import com.nutriplan.shared.data.model.MealAnalysis
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.OptimizePlanRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.repository.AiRepository
import io.ktor.client.network.sockets.ConnectTimeoutException
import io.ktor.client.plugins.HttpRequestTimeoutException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

class AiAdvisorTest {

    private class FakeAi : AiRepository {
        var failure: Throwable? = null
        var gate: CompletableDeferred<Unit>? = null
        val recommendationRequests = mutableListOf<AiRecommendationRequest>()
        val analyzeRequests = mutableListOf<AnalyzeMealRequest>()
        val optimizeRequests = mutableListOf<OptimizePlanRequest>()

        override suspend fun recommendations(request: AiRecommendationRequest): AiRecommendations {
            recommendationRequests += request
            gate?.await()
            failure?.let { throw it }
            return AiRecommendations(reasoning = "Because.", disclaimer = "Not medical advice.")
        }

        override suspend fun analyzeMeal(request: AnalyzeMealRequest): MealAnalysis {
            analyzeRequests += request
            failure?.let { throw it }
            return MealAnalysis(warnings = listOf("High sodium"), disclaimer = "Estimates only.")
        }

        override suspend fun optimizePlan(request: OptimizePlanRequest): MealPlan {
            optimizeRequests += request
            failure?.let { throw it }
            return MealPlan(
                id = request.planId,
                name = "Optimized",
                startDate = "2026-10-01",
                endDate = "2026-10-07",
                dailyCalorieTarget = 2000,
                status = "draft",
            )
        }
    }

    private val ai = FakeAi()
    private val advisor = AiAdvisor(ai)

    private val preferences = DietaryPreferences(
        dietType = "vegan",
        allergies = listOf("peanuts"),
        dailyCalorieTarget = 1800,
        macroTargets = DietaryMacroTargets(proteinGrams = 120),
        excludedIngredients = emptyList(),
        cuisinePreferences = listOf("mexican"),
        appetiteSatisfactionLevel = 3,
    )

    // --- recommendations ---

    @Test
    fun `without ingredients or a meal type the recommendation is for a whole meal plan`() = runTest {
        val result = advisor.recommend(preferences)

        assertIs<AiResult.Success<AiRecommendations>>(result)
        assertEquals("Not medical advice.", result.value.disclaimer)
        assertEquals(AiAdvisor.CONTEXT_MEAL_PLAN, ai.recommendationRequests.single().context)
    }

    @Test
    fun `a meal type makes it a single meal`() = runTest {
        advisor.recommend(preferences, mealType = "dinner")

        val request = ai.recommendationRequests.single()
        assertEquals(AiAdvisor.CONTEXT_SINGLE_MEAL, request.context)
        assertEquals("dinner", request.mealType)
    }

    @Test
    fun `ingredients on hand make it ingredient based and are cleaned up`() = runTest {
        advisor.recommend(preferences, mealType = "lunch", availableIngredients = listOf(" rice ", "", "beans", "rice"))

        val request = ai.recommendationRequests.single()
        assertEquals(AiAdvisor.CONTEXT_INGREDIENTS, request.context)
        assertEquals(listOf("rice", "beans"), request.availableIngredients)
    }

    @Test
    fun `the preferences are sent without the appetite rating and without empty lists`() = runTest {
        advisor.recommend(preferences)

        val sent = ai.recommendationRequests.single().dietaryPreferences!!
        assertEquals("vegan", sent.dietType)
        assertEquals(listOf("peanuts"), sent.allergies)
        assertEquals(1800, sent.dailyCalorieTarget)
        assertEquals(120, sent.macroTargets?.proteinGrams)
        assertNull(sent.excludedIngredients, "an empty list is left out")
        assertEquals(listOf("mexican"), sent.cuisinePreferences)
    }

    @Test
    fun `the calorie target comes from the preferences unless one is given`() = runTest {
        advisor.recommend(preferences)
        advisor.recommend(preferences, calorieTarget = 600)
        advisor.recommend(null)

        assertEquals(listOf(1800, 600, null), ai.recommendationRequests.map { it.calorieTarget })
        assertNull(ai.recommendationRequests.last().dietaryPreferences)
    }

    @Test
    fun `the reply is in the user's language when it is supported and in Spanish otherwise`() = runTest {
        AiAdvisor(ai) { "en-US" }.recommend(null)
        AiAdvisor(ai) { "es" }.recommend(null)
        AiAdvisor(ai) { "fr" }.recommend(null)

        assertEquals(listOf("en", "es", "es"), ai.recommendationRequests.map { it.language })
    }

    // --- meal analysis ---

    @Test
    fun `a meal description is analyzed`() = runTest {
        val result = advisor.analyzeMeal("  Chicken with rice ")

        assertIs<AiResult.Success<MealAnalysis>>(result)
        assertEquals(listOf("High sodium"), result.value.warnings)
        assertEquals("Chicken with rice", ai.analyzeRequests.single().description)
    }

    @Test
    fun `a blank description is refused without calling the service`() = runTest {
        assertEquals(AiResult.Failure(AiError.REJECTED), advisor.analyzeMeal("   "))
        assertTrue(ai.analyzeRequests.isEmpty())
    }

    // --- plan optimization ---

    @Test
    fun `a plan is optimized toward the chosen goal into a draft`() = runTest {
        val result = advisor.optimizePlan("p1", goal = "increase_protein")

        assertIs<AiResult.Success<MealPlan>>(result)
        assertEquals("draft", result.value.status)
        assertEquals(OptimizePlanRequest("p1", "increase_protein"), ai.optimizeRequests.single())
    }

    // --- typed failures ---

    @Test
    fun `failures become typed results instead of exceptions`() = runTest {
        val expected = mapOf<Throwable, AiError>(
            ApiException.NetworkError() to AiError.NETWORK,
            ApiException.HttpError(503, null) to AiError.SERVER_PROBLEM,
            ApiException.HttpError(401, null) to AiError.SESSION_EXPIRED,
            ApiException.HttpError(404, null) to AiError.NOT_FOUND,
            ApiException.HttpError(422, null) to AiError.REJECTED,
            ApiException.HttpError(418, null) to AiError.UNKNOWN,
        )

        expected.forEach { (failure, error) ->
            ai.failure = failure
            assertEquals(AiResult.Failure(error), advisor.optimizePlan("p1"), "for $failure")
            assertEquals(AiResult.Failure(error), advisor.analyzeMeal("Soup"), "for $failure")
            assertEquals(AiResult.Failure(error), advisor.recommend(null), "for $failure")
        }
    }

    @Test
    fun `a slow answer is a timeout not being offline`() = runTest {
        val timedOut = HttpRequestTimeoutException("https://x/ai", 30_000)
        val expected = mapOf<Throwable, AiError>(
            ApiException.NetworkError(errorCause = timedOut) to AiError.TIMEOUT,
            timedOut to AiError.TIMEOUT,
            ApiException.HttpError(504, null) to AiError.TIMEOUT,
            ApiException.NetworkError(errorCause = ConnectTimeoutException("no route")) to AiError.NETWORK,
            ApiException.NetworkError() to AiError.NETWORK,
        )

        expected.forEach { (failure, error) ->
            ai.failure = failure
            assertEquals(AiResult.Failure(error), advisor.recommend(null), "for $failure")
        }
    }

    @Test
    fun `cancelling a request is not turned into a failure`() = runTest {
        ai.gate = CompletableDeferred()
        var outcome: Any? = "not finished"

        val job = launch {
            try {
                outcome = advisor.recommend(null)
            } catch (e: CancellationException) {
                outcome = e
                throw e
            }
        }
        testScheduler.advanceUntilIdle()
        job.cancel()
        job.join()

        assertIs<CancellationException>(outcome)
    }

    @Test
    fun `there are four documented optimization goals`() {
        assertEquals(
            listOf("balance_macros", "increase_protein", "reduce_calories", "increase_satisfaction"),
            AiAdvisor.GOALS,
        )
    }
}
