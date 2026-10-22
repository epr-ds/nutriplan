package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.model.AiRecommendationRequest
import com.nutriplan.shared.data.model.AiRecommendations
import com.nutriplan.shared.data.model.AnalyzeMealRequest
import com.nutriplan.shared.data.model.MealAnalysis
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.OptimizePlanRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.HttpClientProvider
import io.ktor.client.call.body
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.isSuccess
import io.ktor.serialization.ContentConvertException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerializationException

/**
 * Client of the AI Advisor service (`contracts/ai.openapi.yaml`, AIA-601): recipe recommendations,
 * meal analysis and plan optimization. Failures are thrown as [ApiException]; use
 * [com.nutriplan.shared.data.network.toApiFailure] to classify them, or [com.nutriplan.shared.ai.AiAdvisor]
 * for typed results.
 */
interface AiRepository {

    /** Recipes recommended for the request (`POST /ai/recommendations`), with the reasoning. */
    suspend fun recommendations(request: AiRecommendationRequest): AiRecommendations

    /** The estimated nutrition of a described meal (`POST /ai/analyze-meal`). */
    suspend fun analyzeMeal(request: AnalyzeMealRequest): MealAnalysis

    /**
     * An optimized copy of the caller's plan as a reviewable draft (`POST /ai/optimize-plan`); the
     * stored plan is not changed. A plan that does not exist or is not the caller's is a 404.
     */
    suspend fun optimizePlan(request: OptimizePlanRequest): MealPlan
}

class AiRepositoryImpl : AiRepository {

    private val client = HttpClientProvider.client

    override suspend fun recommendations(request: AiRecommendationRequest): AiRecommendations =
        withContext(Dispatchers.IO) {
            client.post("${ApiConfig.AI}/ai/recommendations") { setBody(request) }.readOrThrow()
        }

    override suspend fun analyzeMeal(request: AnalyzeMealRequest): MealAnalysis =
        withContext(Dispatchers.IO) {
            client.post("${ApiConfig.AI}/ai/analyze-meal") { setBody(request) }.readOrThrow()
        }

    override suspend fun optimizePlan(request: OptimizePlanRequest): MealPlan =
        withContext(Dispatchers.IO) {
            client.post("${ApiConfig.AI}/ai/optimize-plan") { setBody(request) }.readOrThrow()
        }

    /**
     * Decodes a 2xx response into [T]; anything else becomes an [ApiException.HttpError] carrying
     * the status and the (problem+json) body, so it classifies by status. A body that does not match
     * the model becomes an [ApiException.SerializationError] instead of an unexplained crash.
     */
    private suspend inline fun <reified T> HttpResponse.readOrThrow(): T {
        if (!status.isSuccess()) {
            throw ApiException.HttpError(statusCode = status.value, body = bodyAsText())
        }
        return try {
            body()
        } catch (e: SerializationException) {
            throw ApiException.SerializationError(errorCause = e)
        } catch (e: ContentConvertException) {
            throw ApiException.SerializationError(errorCause = e)
        }
    }
}
