package com.nutriplan.shared.integration

import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpHandler
import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import java.util.concurrent.CopyOnWriteArrayList

/**
 * A minimal stand-in for the backend gateway, used by the true client↔backend integration tests:
 * a real HTTP server (JDK `HttpServer`) on localhost, so the mobile client performs genuine HTTP
 * through a real socket and engine instead of the in-process
 * [io.ktor.client.engine.mock.MockEngine].
 *
 * Only the endpoints the integration tests exercise are served; anything else is answered 404 the
 * way the real gateway/AI service would for an unknown path.
 */
internal class StubBackendServer {

    private val server: HttpServer = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 8)
    private val requests = CopyOnWriteArrayList<RecordedRequest>()
    private val expectedToken = "integration-test-token"

    fun start() {
        server.createContext("/", HttpHandler { exchange -> handle(exchange) })
        server.start()
    }

    /** Gateway origin the client should point at; the server listens on an ephemeral port. */
    val baseUrl: String
        get() = "http://127.0.0.1:${server.address.port}"

    /** Every request the client sent so far, in arrival order. */
    val received: List<RecordedRequest>
        get() = requests.toList()

    fun stop() {
        server.stop(0)
    }

    private fun handle(exchange: HttpExchange) {
        val method = exchange.requestMethod
        val path = exchange.requestURI.path
        val authorization = exchange.requestHeaders.getFirst("Authorization") ?: ""
        val body = runCatching { exchange.requestBody.readAllBytes().toString(Charsets.UTF_8) }.getOrDefault("")
        requests += RecordedRequest(method, path, authorization, body)

        val response = if (authorization != "Bearer $expectedToken") {
            Response(401, UNAUTHORIZED_RESPONSE)
        } else if (method == "POST" && path == "/ai/v1/recommendations") {
            Response(200, AI_RECOMMENDATIONS_RESPONSE)
        } else if (method == "POST" && path == "/ai/v1/analyze-meal") {
            Response(200, MEAL_ANALYSIS_RESPONSE)
        } else if (method == "POST" && path == "/ai/v1/optimize-plan") {
            Response(200, OPTIMIZE_PLAN_RESPONSE)
        } else if (method == "GET" && path == "/notifications/v1/notifications") {
            Response(200, NOTIFICATION_PAGE_RESPONSE)
        } else if (method == "GET" && path == "/notifications/v1/notifications/unread-count") {
            Response(200, UNREAD_COUNT_RESPONSE)
        } else if (method == "POST" && path.startsWith("/notifications/v1/notifications/")) {
            Response(202, "")
        } else {
            Response(404, NOT_FOUND_RESPONSE)
        }

        val bytes = response.body.toByteArray(Charsets.UTF_8)
        exchange.responseHeaders.add("Content-Type", "application/json")
        exchange.sendResponseHeaders(response.status, bytes.size.toLong())
        if (bytes.isNotEmpty()) {
            exchange.responseBody.use { stream -> stream.write(bytes) }
        }
        exchange.close()
    }

    data class RecordedRequest(
        val method: String,
        val path: String,
        val authorization: String,
        val body: String,
    )

    private data class Response(val status: Int, val body: String)

    private companion object {
        const val EXPECTED_TOKEN = "integration-test-token"

        val AI_RECOMMENDATIONS_RESPONSE = """
            {
              "recommendations": [
                {
                  "id": "recipe-lentil-curry",
                  "name": "Lentil Curry",
                  "description": "Red lentils simmered in coconut milk with spinach.",
                  "ingredients": [ { "name": "red lentils", "quantity": 1.0 } ],
                  "instructions": [ "Simmer until tender." ],
                  "servings": 2,
                  "dietaryTypes": ["vegan", "vegetarian"]
                }
              ],
              "reasoning": "A vegan dinner that fits a 2000 kcal target.",
              "nutritionalAlignment": { "score": 88.0, "details": "Within the calorie target." },
              "disclaimer": "This is not medical advice.",
              "source": "model"
            }
        """.trimIndent()

        val MEAL_ANALYSIS_RESPONSE = """
            {
              "nutritionalInfo": { "calories": 540, "protein": 32.0, "carbs": 60.0, "fat": 12.0, "sugar": 4.0 },
              "alignment": null,
              "warnings": [],
              "disclaimer": "Estimates only."
            }
        """.trimIndent()

        val OPTIMIZE_PLAN_RESPONSE = """
            {
              "id": "plan-1",
              "name": "Week",
              "startDate": "2026-10-01",
              "endDate": "2026-10-07",
              "dailyCalorieTarget": 2000,
              "status": "draft",
              "meals": [],
              "nutritionalSummary": null
            }
        """.trimIndent()

        val NOTIFICATION_PAGE_RESPONSE = """
            {
              "items": [
                {
                  "id": "notif-meal-plan-ready",
                  "type": "meal_plan_ready",
                  "title": "Meal plan ready",
                  "body": "Your meal plan is ready to view.",
                  "payload": { "mealPlanId": "plan-1" },
                  "channels": [ "push" ],
                  "status": "delivered",
                  "createdAt": "2026-11-01T09:00:00Z",
                  "readAt": null,
                  "isRead": false
                }
              ],
              "page": 1,
              "limit": 20,
              "unreadCount": 1,
              "hasMore": false
            }
        """.trimIndent()

        val UNREAD_COUNT_RESPONSE = """{ "unreadCount": 1 }"""

        val UNAUTHORIZED_RESPONSE = """
            { "title": "Unauthorized", "status": 401, "detail": "Missing bearer token" }
        """.trimIndent()

        val NOT_FOUND_RESPONSE = """
            { "title": "Not Found", "status": 404, "detail": "Not Found" }
        """.trimIndent()
    }
}