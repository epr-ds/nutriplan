++ b/mobile/shared/src/commonMain/kotlin/com/nutriplan/shared/data/repository/AiRepository.kt
package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.model.AnalyzeMealRequest
import com.nutriplan.shared.data.model.AnalyzeMealResponse
import com.nutriplan.shared.data.model.OptimizePlanRequest
import com.nutriplan.shared.data.model.OptimizePlanResponse
import com.nutriplan.shared.data.model.RecommendationResult
import com.nutriplan.shared.data.model.RecommendationsRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.HttpClientProvider
import io.ktor.client.call.body
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.HttpStatusCode
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.withContext

/**
 * Repository for AI-related API operations.
 *
 * Covers meal analysis, recipe recommendations, and plan optimization.
 */
interface AiRepository {

    /** Analyze a meal (text description or image). */
    suspend fun analyzeMeal(request: AnalyzeMealRequest): AnalyzeMealResponse

    /** Get AI-powered recipe recommendations. */
    suspend fun getRecommendations(request: RecommendationsRequest): List<RecommendationResult>

    /** Optimize an existing meal plan. */
    suspend fun optimizePlan(request: OptimizePlanRequest): OptimizePlanResponse
}

/**
 * AI service API client implementation.
 */
class AiRepositoryImpl : AiRepository {

    private val client = HttpClientProvider.client

    override suspend fun analyzeMeal(request: AnalyzeMealRequest): AnalyzeMealResponse {
        return withContext(Dispatchers.IO) {
            val response = client.post("${ApiConfig.AI}/ai/analyze-meal") {
                setBody(request)
            }
            handleResponse(response)
        }
    }

    override suspend fun getRecommendations(request: RecommendationsRequest): List<RecommendationResult> {
        return withContext(Dispatchers.IO) {
            val response = client.post("${ApiConfig.AI}/ai/recommendations") {
                setBody(request)
            }
            handleListResponse(response)
        }
    }

    override suspend fun optimizePlan(request: OptimizePlanRequest): OptimizePlanResponse {
        return withContext(Dispatchers.IO) {
            val response = client.post("${ApiConfig.AI}/ai/optimize-plan") {
                setBody(request)
            }
            handleResponse(response)
        }
    }

    private suspend inline fun <reified T> handleResponse(response: io.ktor.client.statement.HttpResponse): T {
        return when (response.status) {
            HttpStatusCode.OK, HttpStatusCode.Created -> response.body()
            HttpStatusCode.Unauthorized -> throw ApiException.create(
                message = "Unauthorized. Please log in again.",
                code = ApiException.Code.UNAUTHORIZED,
            )
            HttpStatusCode.Forbidden -> throw ApiException.create(
                message = "Forbidden. You don't have permission.",
                code = ApiException.Code.FORBIDDEN,
            )
            HttpStatusCode.NotFound -> throw ApiException.create(
                message = "Resource not found.",
                code = ApiException.Code.NOT_FOUND,
            )
            else -> throw ApiException.HttpError(
                statusCode = response.status.value,
                body = response.body<String>(),
            )
        }
    }

    private suspend inline fun <reified T> handleListResponse(response: io.ktor.client.statement.HttpResponse): List<T> {
        return when (response.status) {
            HttpStatusCode.OK -> response.body()
            HttpStatusCode.Unauthorized -> throw ApiException.create(
                message = "Unauthorized. Please log in again.",
                code = ApiException.Code.UNAUTHORIZED,
            )
            else -> throw ApiException.HttpError(
                statusCode = response.status.value,
                body = response.body<String>(),
            )
        }
    }
}
