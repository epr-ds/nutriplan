package com.nutriplan.shared.ai

import com.nutriplan.shared.data.model.AiRecommendationRequest
import com.nutriplan.shared.data.model.AiRecommendations
import com.nutriplan.shared.data.model.AnalyzeMealRequest
import com.nutriplan.shared.data.model.DietaryPreferences
import com.nutriplan.shared.data.model.MealAnalysis
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.NutritionalAlignment
import com.nutriplan.shared.data.model.OptimizePlanRequest
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.repository.AiRepository
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class AiRecommendationsViewModelTest {

    private class FakeAi : AiRepository {
        var failure: Throwable? = null
        val gates = ArrayDeque<CompletableDeferred<Unit>>()
        val requests = mutableListOf<AiRecommendationRequest>()
        val replies = ArrayDeque<AiRecommendations>()

        override suspend fun recommendations(request: AiRecommendationRequest): AiRecommendations {
            requests += request
            val reply = replies.removeFirstOrNull() ?: answer
            gates.removeFirstOrNull()?.await()
            failure?.let { throw it }
            return reply
        }

        override suspend fun analyzeMeal(request: AnalyzeMealRequest): MealAnalysis = error("unused")

        override suspend fun optimizePlan(request: OptimizePlanRequest): MealPlan = error("unused")
    }

    private val ai = FakeAi()
    private var preferences: DietaryPreferences? = DietaryPreferences(dietType = "vegan", dailyCalorieTarget = 1800)
    private val viewModel = AiRecommendationsViewModel(AiAdvisor(ai), preferences = { preferences })

    @Test
    fun `nothing is requested until asked`() {
        val state = viewModel.state.value

        assertFalse(state.hasRequested)
        assertFalse(state.isLoading)
        assertFalse(state.isEmpty)
        assertNull(state.result)
        assertTrue(ai.requests.isEmpty())
    }

    @Test
    fun `a request shows the recipes with the reasoning and the alignment`() = runTest {
        viewModel.recommend()

        val state = viewModel.state.value
        assertEquals(answer, state.result)
        assertTrue(state.hasRequested)
        assertFalse(state.isLoading)
        assertFalse(state.isEmpty)
        assertNull(state.error)
    }

    @Test
    fun `the request carries the saved preferences and what the user chose`() = runTest {
        viewModel.onMealTypeChange("dinner")
        viewModel.onIngredientsChange(" tofu,  rice ,")

        viewModel.recommend()

        val request = ai.requests.single()
        assertEquals("dinner", request.mealType)
        assertEquals(listOf("tofu", "rice"), request.availableIngredients)
        assertEquals("vegan", request.dietaryPreferences?.dietType)
        assertEquals(1800, request.calorieTarget)
    }

    @Test
    fun `the answer remembers the meal it was asked for`() = runTest {
        viewModel.onMealTypeChange("dinner")
        viewModel.recommend()
        viewModel.onMealTypeChange("lunch")

        assertEquals("dinner", viewModel.state.value.resultMealType)

        ai.failure = ApiException.NetworkError()
        viewModel.recommend()
        assertNull(viewModel.state.value.resultMealType)
    }

    @Test
    fun `preferences are read at each request`() = runTest {
        viewModel.recommend()
        preferences = null
        viewModel.recommend()

        assertEquals("vegan", ai.requests[0].dietaryPreferences?.dietType)
        assertNull(ai.requests[1].dietaryPreferences)
    }

    @Test
    fun `an unknown meal type is treated as a whole day`() = runTest {
        viewModel.onMealTypeChange("brunch")
        assertNull(viewModel.state.value.mealType)

        viewModel.onMealTypeChange("lunch")
        viewModel.onMealTypeChange(null)
        viewModel.recommend()

        assertNull(ai.requests.single().mealType)
    }

    @Test
    fun `no recommendations is the empty state`() = runTest {
        ai.replies += AiRecommendations(reasoning = "Nothing fits.", disclaimer = "Not medical advice.")

        viewModel.recommend()

        assertTrue(viewModel.state.value.isEmpty)
    }

    @Test
    fun `a failure clears the previous answer and is shown as a typed error`() = runTest {
        viewModel.recommend()
        ai.failure = ApiException.NetworkError()

        viewModel.recommend()

        val state = viewModel.state.value
        assertEquals(AiError.NETWORK, state.error)
        assertNull(state.result)
        assertFalse(state.isLoading)
        assertFalse(state.isEmpty)
    }

    @Test
    fun `a retry after a failure clears the error`() = runTest {
        ai.failure = ApiException.HttpError(503, null)
        viewModel.recommend()
        assertEquals(AiError.SERVER_PROBLEM, viewModel.state.value.error)

        ai.failure = null
        viewModel.recommend()

        assertNull(viewModel.state.value.error)
        assertEquals(answer, viewModel.state.value.result)
    }

    @Test
    fun `the state is loading while a request runs`() = runTest {
        val gate = CompletableDeferred<Unit>()
        ai.gates += gate

        val job = launch { viewModel.recommend() }
        runCurrent()
        assertTrue(viewModel.state.value.isLoading)

        gate.complete(Unit)
        job.join()
        assertFalse(viewModel.state.value.isLoading)
    }

    @Test
    fun `a slow older answer does not replace a newer one`() = runTest {
        val older = AiRecommendations(recommendations = listOf(Recipe(id = "old", name = "Old")))
        val slow = CompletableDeferred<Unit>()
        ai.replies += older
        ai.replies += answer
        ai.gates += slow
        ai.gates += CompletableDeferred<Unit>().apply { complete(Unit) }

        val first = launch { viewModel.recommend() }
        runCurrent()
        viewModel.recommend()
        slow.complete(Unit)
        first.join()

        assertEquals(answer, viewModel.state.value.result)
        assertFalse(viewModel.state.value.isLoading)
    }

    @Test
    fun `leaving during a request stops the loading`() = runTest {
        ai.gates += CompletableDeferred()

        val job = launch { viewModel.recommend() }
        runCurrent()
        job.cancel()
        job.join()

        assertFalse(viewModel.state.value.isLoading)
        assertNull(viewModel.state.value.error)
    }

    private companion object {
        val answer = AiRecommendations(
            recommendations = listOf(Recipe(id = "r1", name = "Tofu bowl"), Recipe(id = "r2", name = "Lentil soup")),
            reasoning = "High in plant protein.",
            nutritionalAlignment = NutritionalAlignment(score = 86.0, details = "Close to your targets."),
            disclaimer = "Not medical advice.",
        )
    }
}
