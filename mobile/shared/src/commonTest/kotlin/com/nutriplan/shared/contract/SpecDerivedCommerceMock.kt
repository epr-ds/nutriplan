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
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject

/**
 * A Ktor [MockEngine] whose behaviour is derived from [CommerceContract], i.e. from
 * `contracts/commerce.openapi.yaml` (COM-803).
 *
 * Every request is matched against the documented operations: the method and path must be
 * documented; every query parameter must be one the operation declares, the required ones present
 * and enum values allowed; a contract header (`Idempotency-Key`) only where the operation documents
 * it; and a body must carry exactly the schema's fields (all required ones, nothing undocumented,
 * nothing sent as null), enum values allowed, nested objects and array items included. An operation
 * without a body must not get one, and one whose body is optional may go without. The reply is a
 * spec-shaped example with the documented success status. Anything else is answered with a recorded
 * *contract violation*, so a drifted client fails the test.
 */
class SpecDerivedCommerceMock {

    /** Contract violations observed so far. */
    val violations: MutableList<String> = mutableListOf()

    /** The operations that were called, as "METHOD /path-template", in order. */
    val calls: MutableList<String> = mutableListOf()

    /** The last request body that was received, for tests that inspect what was sent. */
    var lastBody: JsonObject? = null
        private set

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    /** Header parameters the contract documents somewhere; each is only allowed where documented. */
    private val contractHeaders = CommerceContract.operations.flatMap { it.headers }.toSet()

    val engine: MockEngine = MockEngine { request -> respondTo(request) }

    private fun MockRequestHandleScope.respondTo(request: HttpRequestData): HttpResponseData {
        val method = request.method.value
        val encodedPath = request.url.encodedPath
        if (!encodedPath.startsWith(CommerceContract.clientPrefix)) {
            return contractError("request outside ${CommerceContract.clientPrefix}: $method $encodedPath")
        }
        val path = encodedPath.removePrefix(CommerceContract.clientPrefix).ifEmpty { "/" }
        val operation = CommerceContract.operations.firstOrNull { it.method == method && matches(it.path, path) }
            ?: return contractError("undocumented operation $method $path")
        val name = "${operation.method} ${operation.path}"
        calls += name

        val before = violations.size
        val parameters = request.url.parameters
        (parameters.names() - operation.query).sorted().let {
            if (it.isNotEmpty()) violations += "$name: undocumented query parameter(s) $it"
        }
        (operation.requiredQuery - parameters.names()).sorted().let {
            if (it.isNotEmpty()) violations += "$name: missing required query parameter(s) $it"
        }
        operation.queryEnums.forEach { (parameter, allowed) ->
            val value = parameters[parameter] ?: return@forEach
            if (value !in allowed) violations += "$name: query $parameter='$value' is not one of ${allowed.sorted()}"
        }
        (contractHeaders.filter { request.headers.contains(it) } - operation.headers).sorted().let {
            if (it.isNotEmpty()) violations += "$name: undocumented header(s) $it"
        }
        val body = (request.body as? TextContent)?.text
        when (val schema = operation.request) {
            null -> if (!body.isNullOrBlank()) violations += "$name: takes no request body"
            else -> if (!body.isNullOrBlank() || operation.bodyRequired) validateBody(schema, body)
        }
        if (violations.size > before) return contractError(violations.last(), record = false)

        val content = operation.response?.let { schema ->
            val one = CommerceResponses.forSchema(schema)
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
        val schema = CommerceContract.schemas.getValue(schemaName)
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
        schema.arrays.forEach { (field, itemSchema) ->
            (obj[field] as? JsonArray)?.forEach { item ->
                if (item is JsonObject) validateObject(itemSchema, item) else violations += "$schemaName.$field: item is not an object"
            }
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
 * property is present (nullable ones as null where the service sends null), so the client is proven
 * to read a complete payload.
 */
internal object CommerceResponses {

    private fun money(amount: String) = """{"amount":$amount,"currency":"MXN","formatted":"MXN $amount"}"""

    private val order =
        """{"id":"11111111-1111-4111-8111-111111111111","status":"pending","fulfillmentType":"grocery_delivery",""" +
            """"provider":{"id":"freshbasket","name":"FreshBasket","type":"grocery",""" +
            """"logoUrl":"https://cdn.nutriplan.mx/providers/freshbasket.png","estimatedDelivery":"Same day, 1-2 h"},""" +
            """"deliveryAddress":{"street":"Reforma 222","apartment":null,"city":"CDMX","state":"CDMX",""" +
            """"zipCode":"06600","country":"MX","instructions":"Ring twice"},""" +
            """"deliveryDate":"2026-11-02","deliveryTimeSlot":"13:00-15:00","createdAt":"2026-10-23T18:00:00Z",""" +
            """"items":[{"name":"Lentil soup","quantity":2,"unit":"serving","unitPrice":${money("89.0")},""" +
            """"lineTotal":${money("178.0")}}],""" +
            """"subtotal":${money("178.0")},"deliveryFee":${money("30.0")},"total":${money("208.0")},""" +
            """"estimatedDelivery":"2026-11-02T13:30:00Z","trackingUrl":"https://track.example/o1",""" +
            """"voucher":{"reference":"9300 1234","amount":${money("208.0")},"expiresAt":"2026-11-01T23:59:00Z",""" +
            """"provider":"conekta","barcodeUrl":"https://pay.example/b.png"},""" +
            """"transfer":{"clabe":"646180157000000004","reference":"REF1","amount":${money("208.0")},""" +
            """"expiresAt":"2026-11-01T23:59:00Z","provider":"conekta"},""" +
            """"approval":{"approvalUrl":"https://paypal.example/a","reference":"PP-1","amount":${money("208.0")},""" +
            """"expiresAt":"2026-11-01T23:59:00Z","provider":"paypal"},""" +
            """"refund":{"refundId":"re_1","status":"partial","amount":${money("50.0")},"provider":"stripe"},""" +
            """"groceryOrder":{"providerId":"freshbasket","externalOrderId":"FB-1001","status":"out_for_delivery"}}"""

    fun forSchema(name: String): String = when (name) {
        "OrderResponse" -> order
        "OrderQuoteResponse" ->
            """{"items":[{"name":"Lentil soup","quantity":2,"unit":"serving","unitPrice":${money("89.0")},""" +
                """"lineTotal":${money("178.0")}}],""" +
                """"subtotal":${money("178.0")},"deliveryFee":${money("30.0")},"total":${money("208.0")}}"""
        "PaymentMethodResponse" ->
            """{"id":"22222222-2222-4222-8222-222222222222","type":"credit_card","brand":"visa","last4":"4242",""" +
                """"expMonth":12,"expYear":2030,"createdAt":"2026-10-01T10:00:00Z"}"""
        "AvailabilityResponse" -> """{"available":true,"zipCode":"06600","timeSlots":["13:00-15:00","19:00-21:00"]}"""
        "ProviderResponse" ->
            """{"id":"freshbasket","name":"FreshBasket","type":"grocery",""" +
                """"logoUrl":"https://cdn.nutriplan.mx/providers/freshbasket.png","estimatedDelivery":"Same day, 1-2 h"}"""
        else -> error("no example response for schema $name")
    }
}
