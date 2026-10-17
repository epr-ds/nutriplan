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
 * A Ktor [MockEngine] whose behaviour is derived from [IdentityContract] (i.e. from
 * `contracts/identity.openapi.yaml`).
 *
 * Every request is matched against the documented operations; the request body is checked to
 * contain exactly the schema's fields; and the reply is a spec-shaped example response. A
 * request the contract does not describe — or one whose body has extra/missing fields — is
 * answered with a recorded *contract violation*, so a drifted client fails the test.
 */
class SpecDerivedIdentityMock {

    /** Contract violations observed so far (cleared per test instance). */
    val violations: MutableList<String> = mutableListOf()

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    val engine: MockEngine = MockEngine { request -> respondTo(request) }

    private fun MockRequestHandleScope.respondTo(request: HttpRequestData): HttpResponseData {
        val path = stripClientPrefix(request.url.encodedPath)
        val method = request.method.value
        val operation = IdentityContract.operations.firstOrNull {
            it.method == method && matches(it.path, path)
        } ?: return contractError("undocumented operation $method $path", record = true)

        operation.requestSchema?.let { schema ->
            validateRequest(schema, (request.body as? TextContent)?.text)
        }
        violations.lastOrNull()?.let { return contractError(it) }

        return respond(
            content = IdentityResponses.forSchema(operation.responseSchema),
            status = HttpStatusCode.fromValue(operation.successStatus),
            headers = jsonHeaders,
        )
    }

    private fun MockRequestHandleScope.contractError(
        message: String,
        record: Boolean = false,
    ): HttpResponseData {
        if (record) violations += message
        return respond(
            content = """{"type":"about:blank","title":"Contract violation","status":400,""" +
                """"detail":"$message"}""",
            status = HttpStatusCode.BadRequest,
            headers = headersOf(HttpHeaders.ContentType, "application/problem+json"),
        )
    }

    private fun validateRequest(schemaName: String, body: String?) {
        val schema = IdentityContract.schemas.getValue(schemaName)
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
    }

    private fun stripClientPrefix(path: String): String {
        if (!path.startsWith(IdentityContract.clientPrefix)) return path
        return path.removePrefix(IdentityContract.clientPrefix).ifEmpty { "/" }
    }

    private fun matches(pattern: String, actual: String): Boolean {
        val patternParts = pattern.trim('/').split('/')
        val actualParts = actual.trim('/').split('/')
        if (patternParts.size != actualParts.size) return false
        return patternParts.zip(actualParts).all { (expected, received) ->
            (expected.startsWith("{") && expected.endsWith("}")) || expected == received
        }
    }
}

/** Canonical example responses shaped exactly like the contract's response schemas. */
internal object IdentityResponses {

    private const val user =
        """{"id":"6f9619ff-8b86-d011-b42d-00cf4fc964ff","email":"ana@example.com",""" +
            """"name":"Ana Rivera","avatarUrl":null,"dietaryPreferences":null,""" +
            """"createdAt":"2026-01-01T00:00:00Z"}"""

    fun forSchema(name: String): String = when (name) {
        "AuthResponse" ->
            """{"accessToken":"access-token","refreshToken":"refresh-token",""" +
                """"expiresIn":900,"user":$user}"""
        "UserProfileResponse" -> user
        "DietaryPreferencesRequest" ->
            """{"dietType":"vegan","allergies":["peanuts"],"dailyCalorieTarget":1800,""" +
                """"macroTargets":{"proteinGrams":120,"carbsGrams":180,"fatGrams":60,""" +
                """"sugarGrams":30},"excludedIngredients":["shellfish"],"cuisinePreferences":["mexican"],"appetiteSatisfactionLevel":3}"""
        "AvatarUploadResponse" ->
            """{"uploadUrl":"https://storage.example/upload","key":"avatars/user/abc.png",""" +
                """"expiresIn":900,"requiredHeaders":{"Content-Type":"image/png"}}"""
        else -> error("no example response for schema $name")
    }
}
