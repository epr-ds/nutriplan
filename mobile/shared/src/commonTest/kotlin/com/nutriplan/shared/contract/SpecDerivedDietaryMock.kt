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
import kotlinx.serialization.json.jsonObject

/**
 * A Ktor [MockEngine] whose behaviour is derived from [DietaryContract], i.e. from
 * `contracts/dietary.openapi.yaml` (DPL-703).
 *
 * Every request is matched against the documented operations: the method and path must be
 * documented, every query parameter must be one the operation declares, a request body must carry
 * exactly the schema's fields (all required ones, nothing undocumented) and an operation without a
 * body must not get one. The reply is a spec-shaped example with the documented success status. A
 * request the contract does not describe is answered with a recorded *contract violation*, so a
 * drifted client fails the test.
 */
class SpecDerivedDietaryMock {

    /** Contract violations observed so far. */
    val violations: MutableList<String> = mutableListOf()

    /** The operations that were called, as "METHOD /path-template", in order. */
    val calls: MutableList<String> = mutableListOf()

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    val engine: MockEngine = MockEngine { request -> respondTo(request) }

    private fun MockRequestHandleScope.respondTo(request: HttpRequestData): HttpResponseData {
        val method = request.method.value
        val encodedPath = request.url.encodedPath
        if (!encodedPath.startsWith(DietaryContract.clientPrefix)) {
            return contractError("request outside ${DietaryContract.clientPrefix}: $method $encodedPath")
        }
        val path = encodedPath.removePrefix(DietaryContract.clientPrefix).ifEmpty { "/" }
        val operation = DietaryContract.operations.firstOrNull { it.method == method && matches(it.path, path) }
            ?: return contractError("undocumented operation $method $path")
        calls += "${operation.method} ${operation.path}"

        val before = violations.size
        val undocumentedQuery = request.url.parameters.names() - operation.query
        if (undocumentedQuery.isNotEmpty()) {
            violations += "${operation.method} ${operation.path}: undocumented query parameter(s) ${undocumentedQuery.sorted()}"
        }
        val body = (request.body as? TextContent)?.text
        when (val schema = operation.request) {
            null -> if (!body.isNullOrBlank()) violations += "${operation.method} ${operation.path}: takes no request body"
            else -> validateRequest(schema, body)
        }
        if (violations.size > before) return contractError(violations.last(), record = false)

        val content = operation.response?.let { schema ->
            val one = DietaryResponses.forSchema(schema)
            if (operation.list) "[$one]" else one
        } ?: ""
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

    private fun validateRequest(schemaName: String, body: String?) {
        val schema = DietaryContract.schemas.getValue(schemaName)
        if (body.isNullOrBlank()) {
            violations += "$schemaName: request body is required"
            return
        }
        val fields = runCatching { json.parseToJsonElement(body).jsonObject.keys }.getOrElse {
            violations += "$schemaName: request body is not a JSON object"
            return
        }
        (schema.required - fields).sorted().let {
            if (it.isNotEmpty()) violations += "$schemaName: missing required field(s) $it"
        }
        (fields - schema.properties).sorted().let {
            if (it.isNotEmpty()) violations += "$schemaName: undocumented field(s) $it"
        }
        // The contract documents that a partial meal update needs at least one field.
        if (schemaName == "UpdateMealRequest" && fields.isEmpty()) {
            violations += "$schemaName: at least one of ${schema.properties.sorted()} is required"
        }
    }

    private fun matches(pattern: String, actual: String): Boolean {
        val patternParts = pattern.trim('/').split('/')
        val actualParts = actual.trim('/').split('/')
        if (patternParts.size != actualParts.size) return false
        return patternParts.zip(actualParts).all { (expected, received) ->
            (expected.startsWith("{") && expected.endsWith("}") && received.isNotEmpty()) || expected == received
        }
    }
}

/**
 * Canonical example responses shaped exactly like the contract's response schemas: every documented
 * property is present (optional ones too, and nullable ones as null where the server sends null),
 * so the client is proven to read a complete payload.
 */
internal object DietaryResponses {

    private const val nutrition =
        """{"calories":365,"protein":14.9,"carbs":57.2,"fat":9.3,"sugar":12.9}"""

    private const val recipe =
        """{"id":"11111111-1111-1111-1111-111111111111","name":"Overnight Oats with Berries",""" +
            """"description":"No-cook oats soaked overnight.",""" +
            """"ingredients":[{"name":"Rolled oats","quantity":80.0,"unit":"g","calories":300,""" +
            """"protein":10.5,"carbs":54.0,"fat":5.0,"sugar":1.2}],""" +
            """"instructions":["Combine oats and milk.","Chill overnight."],"prepTime":5,"cookTime":0,""" +
            """"servings":2,"imageUrl":"https://images.nutriplan.app/recipes/overnight-oats.jpg",""" +
            """"nutritionalInfo":{"calories":243,"protein":9.9,"carbs":38.1,"fat":6.2,"sugar":8.6},""" +
            """"dietaryTypes":["vegetarian","omnivore"]}"""

    private const val plannedMeal =
        """{"id":"22222222-2222-2222-2222-222222222222","mealType":"breakfast","recipe":null,""" +
            """"servings":1.5,"dayIndex":0,"satisfactionLevel":null,"nutritionalInfo":$nutrition}"""

    private const val progressUnknown = """{"target":null,"actual":null,"percentOfTarget":null,"status":null}"""

    private const val summary =
        """{"total":$nutrition,""" +
            """"dailyAverage":{"calories":52,"protein":2.1,"carbs":8.2,"fat":1.3,"sugar":1.8},""" +
            """"targets":{"calories":2000,"protein":150,"carbs":null,"fat":null,"sugar":null},""" +
            """"progress":{"calories":{"target":2000,"actual":52,"percentOfTarget":2.6,"status":"under"},""" +
            """"protein":{"target":150,"actual":2.1,"percentOfTarget":1.4,"status":"under"},""" +
            """"carbs":$progressUnknown,"fat":$progressUnknown,"sugar":$progressUnknown}}"""

    private const val planFields =
        """"id":"33333333-3333-3333-3333-333333333333","name":"Week 40","startDate":"2026-10-01",""" +
            """"endDate":"2026-10-07","status":"draft""""

    fun forSchema(name: String): String = when (name) {
        "MealPlanSummaryResponse" -> "{$planFields}"
        "MealPlanResponse" ->
            """{$planFields,"dailyCalorieTarget":2000,"meals":[$plannedMeal],"nutritionalSummary":$summary}"""
        // The add-meal response is the only one that embeds the recipe.
        "MealResponse" ->
            """{"id":"44444444-4444-4444-4444-444444444444","mealType":"lunch","recipe":$recipe,""" +
                """"servings":1.0,"dayIndex":null,"satisfactionLevel":null,"nutritionalInfo":$nutrition}"""
        "RecipeResponse" -> recipe
        "NutritionDisclaimerResponse" ->
            """{"disclaimer":"Nutrition values are estimates and not medical advice.","medicalAdvice":false,""" +
                """"sources":[{"id":"usda-fdc","name":"USDA FoodData Central","url":"https://fdc.nal.usda.gov",""" +
                """"verified":true}],"fieldSources":{"calories":"usda-fdc","protein":"usda-fdc",""" +
                """"carbs":"usda-fdc","fat":"usda-fdc","sugar":"usda-fdc"},"lastReviewed":"2026-09-01"}"""
        else -> error("no example response for schema $name")
    }
}
