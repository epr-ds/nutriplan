package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.model.AiRecommendationRequest
import com.nutriplan.shared.data.model.AiRecommendations
import com.nutriplan.shared.data.model.AnalyzeMealRequest
import com.nutriplan.shared.data.model.MealAnalysis
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.OptimizePlanRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.BearerTokenRefresher
import com.nutriplan.shared.data.network.HttpClientFactory
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
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
 *
 * Session expiry (AIA-60x) is handled here, on the AI edge: a 401 makes the advisor refresh the
 * session once and retry the same call, so a renewed token recovers the in-flight answer instead of
 * surfacing a dead session to the user directly.
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

class AiRepositoryImpl(
    private val client: HttpClient? = null,
    private val authRepository: AuthRepository = AuthRepository.instance,
    private val refresher: BearerTokenRefresher = BearerTokenRefresher(authRepository),
) : AiRepository {

    /**
     * AI-only HTTP client; defaults to one without the auth plugin so this edge owns its bearer
     * tokens and its session-expiry recovery.
     */
    private val resolvedClient: HttpClient = client ?: HttpClientFactory.create(OkHttp.create { })

    override suspend fun recommendations(request: AiRecommendationRequest): AiRecommendations =
        aiCall {
            resolvedClient.post("${ApiConfig.AI}/recommendations") {
                setBody(request)
                authRepository.currentAccessToken?.let { accessToken ->
                    header(HttpHeaders.Authorization, "Bearer $accessToken")
                }
            }
        }

    override suspend fun analyzeMeal(request: AnalyzeMealRequest): MealAnalysis =
        aiCall {
            resolvedClient.post("${ApiConfig.AI}/analyze-meal") {
                setBody(request)
                authRepository.currentAccessToken?.let { accessToken ->
                    header(HttpHeaders.Authorization, "Bearer $accessToken")
                }
            }
        }

    override suspend fun optimizePlan(request: OptimizePlanRequest): MealPlan =
        aiCall {
            resolvedClient.post("${ApiConfig.AI}/optimize-plan") {
                setBody(request)
                authRepository.currentAccessToken?.let { accessToken ->
                    header(HttpHeaders.Authorization, "Bearer $accessToken")
                }
            }
        }

    /**
     * Sends one AI request, refreshing and retrying once when the session answers 401. Any other
     * failure is decoded as before.
     */
    private suspend inline fun <reified T> aiCall(crossinline block: suspend () -> HttpResponse): T {
        var response = withContext(Dispatchers.IO) { block() }
        if (response.status.isSuccess()) {
            return response.readOrThrow()
        }
        val failure = ApiException.HttpError(statusCode = response.status.value, body = response.bodyAsText())
        if (response.status.value != HttpStatusCode.Unauthorized.value) {
            throw failure
        }
        // The session expired: refresh once and retry the same call with the new tokens.
        val staleRefreshToken = authRepository.currentRefreshToken
        if (staleRefreshToken != null) {
            refresher.refresh(staleRefreshToken)
        }
        response = withContext(Dispatchers.IO) { block() }
        if (response.status.isSuccess()) {
            return response.readOrThrow()
        }
        throw ApiException.HttpError(statusCode = response.status.value, body = response.bodyAsText())
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
