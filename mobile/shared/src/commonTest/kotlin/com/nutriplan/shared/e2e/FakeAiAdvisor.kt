package com.nutriplan.shared.e2e

import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * A stand-in for the AI Advisor's recommendations for the AI journey (AIA-705).
 *
 * The "model" proposes [proposals] in that order, whatever the request says, so an unsafe recipe can
 * come first. Like the service, a deterministic post-filter then removes every recipe whose
 * ingredients contain one of the request's allergies or excluded ingredients (lexical,
 * case-insensitive, tolerant of a plural `s`; `services/ai/app/recommendations/safety.py`). So the
 * journey only gets a safe recipe if the app really sends the user's allergies. Responses follow
 * `contracts/ai.openapi.yaml`.
 */
class FakeAiAdvisor(private val proposals: List<FakeDietaryBackend.CatalogRecipe>) {

    private val json = Json { ignoreUnknownKeys = true }
    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    /** The body of every recommendation request, in order. */
    val recommendationRequests: MutableList<JsonObject> = mutableListOf()

    /** Whether [path] (the full request path) is for this service. */
    fun handles(path: String): Boolean = path.startsWith(PREFIX)

    fun MockRequestHandleScope.handle(
        request: HttpRequestData,
        recipeJson: (FakeDietaryBackend.CatalogRecipe) -> JsonElement,
    ): HttpResponseData {
        val path = request.url.encodedPath.removePrefix(PREFIX)
        if (request.method.value != "POST" || path != "/ai/recommendations") {
            return respond(PROBLEM_404, HttpStatusCode.NotFound, jsonHeaders)
        }
        val body = json.parseToJsonElement((request.body as TextContent).text).jsonObject
        recommendationRequests += body

        val preferences = body["dietaryPreferences"]?.jsonObject
        val forbidden = listOf("allergies", "excludedIngredients")
            .flatMap { key -> preferences?.get(key)?.jsonArray.orEmpty().map { it.jsonPrimitive.content } }
        val safe = proposals.filter { recipe -> forbidden.none { term -> recipe.contains(term) } }

        val answer = buildJsonObject {
            put("recommendations", JsonArray(safe.map(recipeJson)))
            put("reasoning", "Picked for your preferences.")
            put("nutritionalAlignment", buildJsonObject { put("score", 80.0) })
            put("disclaimer", "Not medical advice.")
        }
        return respond(answer.toString(), HttpStatusCode.OK, jsonHeaders)
    }

    private companion object {
        const val PREFIX = "/ai/v1"
        const val PROBLEM_404 = """{"type":"about:blank","title":"Not Found","status":404}"""
    }
}

/** Whether any ingredient of this recipe contains [term] (case-insensitive, singular or plural). */
fun FakeDietaryBackend.CatalogRecipe.contains(term: String): Boolean {
    val stem = term.trim().lowercase().removeSuffix("s")
    return stem.isNotEmpty() && ingredients.any { it.lowercase().contains(stem) }
}
