package com.nutriplan.shared.contract

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject

/**
 * A Ktor [MockEngine] whose behaviour is derived from [AiContract], i.e. from
 * `contracts/ai.openapi.yaml` (AIA-703).
 *
 * Every request must be a documented operation; its body must carry exactly the schema's fields (all
 * required ones, nothing undocumented, nested objects included), and enum fields must hold one of the
 * documented values. The reply is a spec-shaped example with the documented success status. Anything
 * else is answered with a recorded *contract violation*, so a drifted client fails the test.
 */
class SpecDerivedAiMock {

    /** Contract violations observed so far. */
    val violations: MutableList<String> = mutableListOf()

    /** The operations that were called, as "METHOD /path", in order. */
    val calls: MutableList<String> = mutableListOf()

    /** The last request body that was received, for tests that inspect what was sent. */
    var lastBody: JsonObject? = null
        private set

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    val engine: MockEngine = MockEngine { request -> respondTo(request) }

    private fun MockRequestHandleScope.respondTo(request: HttpRequestData): HttpResponseData {
        val method = request.method.value
        val encodedPath = request.url.encodedPath
        if (!encodedPath.startsWith(AiContract.clientPrefix)) {
            return contractError("request outside ${AiContract.clientPrefix}: $method $encodedPath")
        }
        val path = encodedPath.removePrefix(AiContract.clientPrefix)
        val operation = AiContract.operations.firstOrNull { it.method == method && it.path == path }
            ?: return contractError("undocumented operation $method $path")
        calls += "${operation.method} ${operation.path}"

        val before = violations.size
        if (request.url.parameters.names().isNotEmpty()) {
            violations += "$method $path: takes no query parameters, got ${request.url.parameters.names().sorted()}"
        }
        val body = (request.body as? TextContent)?.text
        operation.request?.let { validateBody(it, body) }
        if (violations.size > before) return contractError(violations.last(), record = false)

        val content = operation.response?.let(AiResponses::forSchema).orEmpty()
        return respond(content = content, status = HttpStatusCode.fromValue(operation.status), headers = jsonHeaders)
    }

    private fun MockRequestHandleScope.contractError(message: String, record: Boolean = true): HttpResponseData {
        if (record) violations += message
        return respond(
            content = """{"type":"about:blank","title":"Contract violation","status":400,"detail":"${message.replace("\"", "'")}"}""",
            status = HttpStatusCode.BadRequest,
            headers = headersOf(HttpHeaders.ContentType, "application/problem+json"),
        )
    }

    private fun validateBody(schemaName: String, body: String?) {
        if (body.isNullOrBlank()) {
            violations += "$schemaName: request body is required"
            return
        }
        val obj = runCatching { json.parseToJsonElement(body).jsonObject }.getOrElse {
            violations += "$schemaName: request body is not a JSON object"
            return
        }
        lastBody = obj
        validateObject(schemaName, obj)
    }

    private fun validateObject(schemaName: String, obj: JsonObject) {
        val schema = AiContract.schemas.getValue(schemaName)
        (schema.required - obj.keys).sorted().let {
            if (it.isNotEmpty()) violations += "$schemaName: missing required field(s) $it"
        }
        (obj.keys - schema.properties).sorted().let {
            if (it.isNotEmpty()) violations += "$schemaName: undocumented field(s) $it"
        }
        // Optional fields are left out rather than sent as null.
        obj.filterValues { it is JsonNull }.keys.sorted().let {
            if (it.isNotEmpty()) violations += "$schemaName: field(s) sent as null instead of left out $it"
        }
        schema.enums.forEach { (field, allowed) ->
            val value = (obj[field] as? JsonPrimitive)?.takeIf { it.isString }?.content ?: return@forEach
            if (value !in allowed) violations += "$schemaName.$field: '$value' is not one of ${allowed.sorted()}"
        }
        schema.nested.forEach { (field, nestedSchema) ->
            (obj[field] as? JsonObject)?.let { validateObject(nestedSchema, it) }
        }
    }
}

/** Canonical example responses shaped exactly like the AI contract's response schemas. */
internal object AiResponses {

    private const val recipe =
        """{"id":"r1","name":"Lentil Soup","description":null,""" +
            """"ingredients":[{"name":"Lentils","quantity":200,"unit":"g","calories":230,"protein":18,""" +
            """"carbs":40,"fat":1,"sugar":2}],"instructions":["Simmer for 20 minutes."],"prepTime":10,""" +
            """"cookTime":20,"servings":2,"imageUrl":null,""" +
            """"nutritionalInfo":{"calories":320,"protein":19.5,"carbs":41,"fat":3,"sugar":4},""" +
            """"dietaryTypes":["vegan","vegetarian"]}"""

    fun forSchema(name: String): String = when (name) {
        "AIRecommendationResponse" ->
            """{"recommendations":[$recipe],"reasoning":"High protein and plant based.",""" +
                """"nutritionalAlignment":{"score":87.5,"details":"Close to your protein target."},""" +
                """"disclaimer":"This is not medical advice."}"""
        "NutritionalAnalysisResponse" ->
            """{"nutritionalInfo":{"calories":540,"protein":32.0,"carbs":55.0,"fat":18.0,"sugar":null},""" +
                """"alignment":{"score":72.0,"details":"A little over your fat target."},""" +
                """"warnings":["High in sodium"],"disclaimer":"Estimates only, not medical advice."}"""
        "MealPlanResponse" ->
            """{"id":"p1","name":"Week 40 (optimized)","startDate":"2026-10-01","endDate":"2026-10-07",""" +
                """"dailyCalorieTarget":2000,"status":"draft",""" +
                """"meals":[{"id":"m1","mealType":"lunch","servings":1.5,"recipe":null,""" +
                """"nutritionalInfo":{"calories":480,"protein":30,"carbs":50,"fat":15,"sugar":5}}],""" +
                """"nutritionalSummary":{"total":{"calories":480,"protein":30,"carbs":50,"fat":15,"sugar":5},""" +
                """"dailyAverage":{"calories":69,"protein":4.3,"carbs":7.1,"fat":2.1,"sugar":0.7},""" +
                """"targets":{"calories":2000,"protein":150,"carbs":null,"fat":null,"sugar":null}}}"""
        else -> error("no example response for schema $name")
    }
}
