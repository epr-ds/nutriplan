package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.MealPlanQuery
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
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * [DietaryRepositoryImpl] against the Dietary API contract: the request it sends (method, path,
 * query, body), how it decodes contract-shaped responses, and how every kind of failure is
 * classified. A [MockEngine] stands in for the server.
 */
class DietaryRepositoryContractTest {

    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")
    private val problemHeaders = headersOf(HttpHeaders.ContentType, "application/problem+json")

    private var lastRequest: HttpRequestData? = null

    @AfterTest
    fun tearDown() = HttpClientProvider.reset()

    private fun serve(
        status: HttpStatusCode = HttpStatusCode.OK,
        body: String = "{}",
        headers: io.ktor.http.Headers = jsonHeaders,
    ): DietaryRepositoryImpl {
        HttpClientProvider.create(
            MockEngine { request ->
                lastRequest = request
                respond(content = body, status = status, headers = headers)
            },
            authRepository = null,
        )
        return DietaryRepositoryImpl()
    }

    private fun requestBody(): String = (lastRequest!!.body as TextContent).text

    // --- requests ---

    @Test
    fun `listing asks for the contract's paging and status parameters`() = runTest {
        val repository = serve(body = "[]")

        repository.getMealPlans(MealPlanQuery(status = "active", page = 2, limit = 10))

        val request = lastRequest!!
        assertEquals(HttpMethod.Get, request.method)
        assertEquals("/dietary/v1/meal-plans", request.url.encodedPath)
        assertEquals("active", request.url.parameters["status"])
        assertEquals("2", request.url.parameters["page"])
        assertEquals("10", request.url.parameters["limit"])
        assertNull(request.url.parameters["offset"])
    }

    @Test
    fun `listing without a query sends no parameters`() = runTest {
        val repository = serve(body = "[]")

        repository.getMealPlans()

        assertTrue(lastRequest!!.url.parameters.isEmpty())
    }

    @Test
    fun `get plan reads the plan by id`() = runTest {
        val repository = serve(body = PLAN_JSON)

        val plan = repository.getMealPlan("p1")

        assertEquals(HttpMethod.Get, lastRequest!!.method)
        assertEquals("/dietary/v1/meal-plans/p1", lastRequest!!.url.encodedPath)
        assertEquals("Week 40", plan.name)
        assertEquals(2000, plan.dailyCalorieTarget)
        assertEquals(1, plan.meals.size)
    }

    @Test
    fun `create posts the contract body and decodes the 201`() = runTest {
        val repository = serve(status = HttpStatusCode.Created, body = PLAN_JSON)

        val plan = repository.createMealPlan(
            CreateMealPlanRequest(
                name = "Week 40",
                startDate = "2026-10-01",
                endDate = "2026-10-07",
                dailyCalorieTarget = 2000,
            ),
        )

        assertEquals(HttpMethod.Post, lastRequest!!.method)
        assertEquals("/dietary/v1/meal-plans", lastRequest!!.url.encodedPath)
        assertTrue("\"dailyCalorieTarget\":2000" in requestBody(), requestBody())
        assertEquals("p1", plan.id)
    }

    @Test
    fun `status change patches the plan with only the status`() = runTest {
        val repository = serve(body = PLAN_JSON)

        repository.updateMealPlanStatus("p1", "active")

        assertEquals(HttpMethod.Patch, lastRequest!!.method)
        assertEquals("/dietary/v1/meal-plans/p1", lastRequest!!.url.encodedPath)
        assertEquals("""{"status":"active"}""", requestBody())
    }

    @Test
    fun `add meal posts servings and decodes the meal with its recipe`() = runTest {
        val repository = serve(
            status = HttpStatusCode.Created,
            body = """{"id":"m9","mealType":"lunch","servings":1.5,"dayIndex":null,"recipe":{"id":"r1","name":"Soup"},"nutritionalInfo":null}""",
        )

        val meal = repository.addMeal("p1", AddMealRequest(mealType = "lunch", recipeId = "r1", servings = 1.5))

        assertEquals(HttpMethod.Post, lastRequest!!.method)
        assertEquals("/dietary/v1/meal-plans/p1/meals", lastRequest!!.url.encodedPath)
        assertEquals("""{"mealType":"lunch","recipeId":"r1","servings":1.5}""", requestBody())
        assertEquals("Soup", meal.recipe?.name)
    }

    // --- failures ---

    @Test
    fun `every HTTP failure is thrown as an HttpError that classifies by status`() = runTest {
        val expected = mapOf(
            HttpStatusCode.Unauthorized to ApiFailure.SESSION_EXPIRED,
            HttpStatusCode.Forbidden to ApiFailure.FORBIDDEN,
            HttpStatusCode.NotFound to ApiFailure.NOT_FOUND,
            HttpStatusCode.Conflict to ApiFailure.CONFLICT,
            HttpStatusCode.UnprocessableEntity to ApiFailure.REJECTED,
            HttpStatusCode.InternalServerError to ApiFailure.SERVER,
            HttpStatusCode.ServiceUnavailable to ApiFailure.SERVER,
        )

        expected.forEach { (status, failure) ->
            val repository = serve(status = status, body = PROBLEM_JSON, headers = problemHeaders)
            val error = assertFailsWith<ApiException.HttpError>("status ${status.value}") {
                repository.getMealPlan("p1")
            }
            assertEquals(status.value, error.statusCode)
            assertEquals(failure, error.toApiFailure(), "status ${status.value}")
        }
    }

    @Test
    fun `the problem body of a validation failure is kept`() = runTest {
        val repository = serve(
            status = HttpStatusCode.UnprocessableEntity,
            body = """{"title":"Unprocessable","status":422,"errors":[{"field":"endDate"}]}""",
            headers = problemHeaders,
        )

        val error = assertFailsWith<ApiException.HttpError> {
            repository.createMealPlan(CreateMealPlanRequest("x", "2026-10-02", "2026-10-01", 2000))
        }

        assertTrue("endDate" in error.body.orEmpty(), error.body)
    }

    @Test
    fun `a response that does not match the model is a serialization error, not a crash`() = runTest {
        val repository = serve(body = """{"unexpected":true}""")

        val error = assertFailsWith<ApiException.SerializationError> { repository.getMealPlan("p1") }

        assertEquals(ApiFailure.UNKNOWN, error.toApiFailure())
    }

    @Test
    fun `a connection failure is thrown as a network error and classifies as offline`() = runTest {
        HttpClientProvider.create(
            MockEngine { throw IOException("no route to host") },
            authRepository = null,
        )
        val repository = DietaryRepositoryImpl()

        val error = assertFailsWith<ApiException.NetworkError> { repository.getMealPlans() }

        assertEquals(ApiFailure.OFFLINE, error.toApiFailure())
    }

    private companion object {
        const val PROBLEM_JSON = """{"type":"about:blank","title":"Problem","status":0}"""

        val PLAN_JSON = """
            {
              "id":"p1","name":"Week 40","startDate":"2026-10-01","endDate":"2026-10-07",
              "dailyCalorieTarget":2000,"status":"draft",
              "meals":[{"id":"m1","mealType":"lunch","servings":1.0,"dayIndex":0,"satisfactionLevel":null,
                        "recipe":null,"nutritionalInfo":{"calories":500,"protein":30.0,"carbs":50.0,"fat":15.0,"sugar":5.0}}],
              "nutritionalSummary":{
                "total":{"calories":500,"protein":30.0,"carbs":50.0,"fat":15.0,"sugar":5.0},
                "dailyAverage":{"calories":71,"protein":4.0,"carbs":7.0,"fat":2.0,"sugar":0.7},
                "targets":{"calories":2000,"protein":null,"carbs":null,"fat":null,"sugar":null},
                "progress":{
                  "calories":{"target":2000.0,"actual":71.0,"percentOfTarget":3.5,"status":"under"},
                  "protein":{"target":null,"actual":null,"percentOfTarget":null,"status":null},
                  "carbs":{"target":null,"actual":null,"percentOfTarget":null,"status":null},
                  "fat":{"target":null,"actual":null,"percentOfTarget":null,"status":null},
                  "sugar":{"target":null,"actual":null,"percentOfTarget":null,"status":null}
                }
              }
            }
        """.trimIndent()
    }
}
