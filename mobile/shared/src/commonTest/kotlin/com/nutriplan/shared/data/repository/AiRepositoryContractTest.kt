package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.model.AiRecommendationRequest
import com.nutriplan.shared.data.model.AnalyzeMealRequest
import com.nutriplan.shared.data.model.OptimizePlanRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.network.toApiFailure
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import io.ktor.utils.io.errors.IOException
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/**
 * [AiRepositoryImpl] against `contracts/ai.openapi.yaml` (AIA-601): the request it sends (method,
 * path, body), how it reads contract-shaped responses, and how failures are classified. A
 * [MockEngine] stands in for the AI service.
 */
class AiRepositoryContractTest {

    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")
    private val problemHeaders = headersOf(HttpHeaders.ContentType, "application/problem+json")

    private var lastRequest: HttpRequestData? = null

    @AfterTest
    fun tearDown() = HttpClientProvider.reset()

    private fun serve(status: HttpStatusCode = HttpStatusCode.OK, body: String = "{}"): AiRepositoryImpl {
        HttpClientProvider.create(
            MockEngine { request ->
                lastRequest = request
                respond(content = body, status = status, headers = if (status.value < 400) jsonHeaders else problemHeaders)
            },
            authRepository = null,
        )
        return AiRepositoryImpl()
    }

    private fun requestBody(): String = (lastRequest!!.body as TextContent).text

    @Test
    fun `recommendations posts the request and reads the response object`() = runTest {
        val repository = serve(
            body = """{"recommendations":[{"id":"r1","name":"Soup","servings":2,"ingredients":[],""" +
                """"instructions":[],"dietaryTypes":["vegan"]}],"reasoning":"Light.","disclaimer":"Not medical advice."}""",
        )

        val result = repository.recommendations(AiRecommendationRequest(context = "single_meal", mealType = "dinner"))

        assertEquals(HttpMethod.Post, lastRequest!!.method)
        assertEquals("/ai/v1/ai/recommendations", lastRequest!!.url.encodedPath)
        assertEquals("""{"context":"single_meal","mealType":"dinner","language":"es"}""", requestBody())
        assertEquals("Soup", result.recommendations.single().name)
        assertEquals("Not medical advice.", result.disclaimer)
    }

    @Test
    fun `analyzing a meal posts the description and reads the analysis`() = runTest {
        val repository = serve(
            body = """{"nutritionalInfo":{"calories":540,"protein":32.0},"alignment":null,""" +
                """"warnings":["High sodium"],"disclaimer":"Estimates only."}""",
        )

        val analysis = repository.analyzeMeal(AnalyzeMealRequest("Chicken with rice"))

        assertEquals("/ai/v1/ai/analyze-meal", lastRequest!!.url.encodedPath)
        assertEquals("""{"description":"Chicken with rice"}""", requestBody())
        assertEquals(540, analysis.nutritionalInfo?.calories)
        assertEquals(listOf("High sodium"), analysis.warnings)
    }

    @Test
    fun `optimizing a plan posts the plan id and goal and reads the draft plan`() = runTest {
        val repository = serve(
            body = """{"id":"p1","name":"Week","startDate":"2026-10-01","endDate":"2026-10-07",""" +
                """"dailyCalorieTarget":2000,"status":"draft","meals":[],"nutritionalSummary":null}""",
        )

        val plan = repository.optimizePlan(OptimizePlanRequest("p1", goal = "reduce_calories"))

        assertEquals("/ai/v1/ai/optimize-plan", lastRequest!!.url.encodedPath)
        assertEquals("""{"planId":"p1","goal":"reduce_calories"}""", requestBody())
        assertEquals("draft", plan.status)
    }

    @Test
    fun `every documented failure is thrown as an HttpError that classifies by status`() = runTest {
        val expected = mapOf(
            HttpStatusCode.Unauthorized to ApiFailure.SESSION_EXPIRED,
            HttpStatusCode.NotFound to ApiFailure.NOT_FOUND,
            HttpStatusCode.UnprocessableEntity to ApiFailure.REJECTED,
            HttpStatusCode.ServiceUnavailable to ApiFailure.SERVER,
        )

        expected.forEach { (status, failure) ->
            val repository = serve(status = status, body = """{"type":"about:blank","title":"x","status":${status.value}}""")
            val error = assertFailsWith<ApiException.HttpError>("status ${status.value}") {
                repository.optimizePlan(OptimizePlanRequest("p1"))
            }
            assertEquals(failure, error.toApiFailure(), "status ${status.value}")
        }
    }

    @Test
    fun `a reply that does not match the contract is a serialization error`() = runTest {
        // The old client expected a bare list here; the contract returns an object.
        val repository = serve(body = """[{"recipeId":"r1","recipeName":"Soup"}]""")

        assertFailsWith<ApiException.SerializationError> {
            repository.recommendations(AiRecommendationRequest(context = "meal_plan"))
        }
    }

    @Test
    fun `a dropped connection is a network error`() = runTest {
        HttpClientProvider.create(MockEngine { throw IOException("no route to host") }, authRepository = null)

        val error = assertFailsWith<ApiException.NetworkError> {
            AiRepositoryImpl().analyzeMeal(AnalyzeMealRequest("Soup"))
        }

        assertEquals(ApiFailure.OFFLINE, error.toApiFailure())
    }
}
