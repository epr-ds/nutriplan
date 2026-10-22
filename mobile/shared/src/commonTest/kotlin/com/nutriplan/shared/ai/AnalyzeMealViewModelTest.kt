package com.nutriplan.shared.ai

import com.nutriplan.shared.data.model.AiRecommendationRequest
import com.nutriplan.shared.data.model.AiRecommendations
import com.nutriplan.shared.data.model.AnalyzeMealRequest
import com.nutriplan.shared.data.model.MealAnalysis
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.OptimizePlanRequest
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

class AnalyzeMealViewModelTest {

    private class FakeAi : AiRepository {
        var failure: Throwable? = null
        val gates = ArrayDeque<CompletableDeferred<Unit>>()
        val replies = ArrayDeque<MealAnalysis>()
        val requests = mutableListOf<AnalyzeMealRequest>()

        override suspend fun analyzeMeal(request: AnalyzeMealRequest): MealAnalysis {
            requests += request
            val reply = replies.removeFirstOrNull() ?: analysis
            gates.removeFirstOrNull()?.await()
            failure?.let { throw it }
            return reply
        }

        override suspend fun recommendations(request: AiRecommendationRequest): AiRecommendations = error("unused")

        override suspend fun optimizePlan(request: OptimizePlanRequest): MealPlan = error("unused")
    }

    private val ai = FakeAi()
    private val viewModel = AnalyzeMealViewModel(AiAdvisor(ai))

    @Test
    fun `nothing is analyzed until asked`() {
        val state = viewModel.state.value

        assertFalse(state.canAnalyze)
        assertNull(state.result)
        assertTrue(ai.requests.isEmpty())
    }

    @Test
    fun `a described meal is analyzed with its nutrition and warnings`() = runTest {
        viewModel.onDescriptionChange("  Two eggs and toast  ")
        assertTrue(viewModel.state.value.canAnalyze)

        viewModel.analyze()

        assertEquals("Two eggs and toast", ai.requests.single().description)
        val state = viewModel.state.value
        assertEquals(analysis, state.result)
        assertEquals("Two eggs and toast", state.analyzedDescription)
        assertFalse(state.isAnalyzing)
        assertNull(state.error)
    }

    @Test
    fun `a blank description is not sent and says what is missing`() = runTest {
        viewModel.onDescriptionChange("   ")

        viewModel.analyze()

        assertTrue(ai.requests.isEmpty())
        assertTrue(viewModel.state.value.descriptionMissing)
        assertFalse(viewModel.state.value.canAnalyze)
    }

    @Test
    fun `typing clears the missing description message`() = runTest {
        viewModel.analyze()

        viewModel.onDescriptionChange("Soup")

        assertFalse(viewModel.state.value.descriptionMissing)
    }

    @Test
    fun `a very long description is cut`() {
        viewModel.onDescriptionChange("a".repeat(AnalyzeMealViewModel.MAX_DESCRIPTION_LENGTH + 20))

        assertEquals(AnalyzeMealViewModel.MAX_DESCRIPTION_LENGTH, viewModel.state.value.description.length)
    }

    @Test
    fun `a failure clears the previous analysis and is a typed error`() = runTest {
        viewModel.onDescriptionChange("Soup")
        viewModel.analyze()
        ai.failure = ApiException.HttpError(503, null)

        viewModel.analyze()

        val state = viewModel.state.value
        assertEquals(AiError.SERVER_PROBLEM, state.error)
        assertNull(state.result)
        assertNull(state.analyzedDescription)
        assertFalse(state.isAnalyzing)
    }

    @Test
    fun `a retry after a failure clears the error`() = runTest {
        viewModel.onDescriptionChange("Soup")
        ai.failure = ApiException.NetworkError()
        viewModel.analyze()
        assertEquals(AiError.NETWORK, viewModel.state.value.error)

        ai.failure = null
        viewModel.analyze()

        assertNull(viewModel.state.value.error)
        assertEquals(analysis, viewModel.state.value.result)
    }

    @Test
    fun `the state is analyzing while a request runs`() = runTest {
        val gate = CompletableDeferred<Unit>()
        ai.gates += gate
        viewModel.onDescriptionChange("Soup")

        val job = launch { viewModel.analyze() }
        runCurrent()
        assertTrue(viewModel.state.value.isAnalyzing)
        assertFalse(viewModel.state.value.canAnalyze)

        gate.complete(Unit)
        job.join()
        assertFalse(viewModel.state.value.isAnalyzing)
    }

    @Test
    fun `a slow older answer does not replace a newer one`() = runTest {
        val older = MealAnalysis(warnings = listOf("Old"))
        val slow = CompletableDeferred<Unit>()
        ai.replies += older
        ai.replies += analysis
        ai.gates += slow
        ai.gates += CompletableDeferred<Unit>().apply { complete(Unit) }
        viewModel.onDescriptionChange("Soup")

        val first = launch { viewModel.analyze() }
        runCurrent()
        viewModel.onDescriptionChange("Salad")
        viewModel.analyze()
        slow.complete(Unit)
        first.join()

        assertEquals(analysis, viewModel.state.value.result)
        assertEquals("Salad", viewModel.state.value.analyzedDescription)
    }

    @Test
    fun `leaving during a request stops the analyzing`() = runTest {
        ai.gates += CompletableDeferred()
        viewModel.onDescriptionChange("Soup")

        val job = launch { viewModel.analyze() }
        runCurrent()
        job.cancel()
        job.join()

        assertFalse(viewModel.state.value.isAnalyzing)
        assertNull(viewModel.state.value.error)
    }

    private companion object {
        val analysis = MealAnalysis(
            nutritionalInfo = NutritionalInfo(calories = 420, protein = 24.0, carbs = 30.0, fat = 20.0),
            warnings = listOf("High in saturated fat"),
            disclaimer = "Estimates only.",
        )
    }
}
