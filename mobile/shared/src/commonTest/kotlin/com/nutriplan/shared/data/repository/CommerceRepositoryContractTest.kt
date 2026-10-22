package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.model.CancelOrderRequest
import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.GrocerySearchItem
import com.nutriplan.shared.data.model.GrocerySearchRequest
import com.nutriplan.shared.data.model.OrderAddress
import com.nutriplan.shared.data.model.OrderListQuery
import com.nutriplan.shared.data.model.PaymentMethodRequest
import com.nutriplan.shared.data.model.SavePaymentMethodRequest
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
import io.ktor.http.content.OutgoingContent
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import io.ktor.utils.io.errors.IOException
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertNull

/**
 * [CommerceRepositoryImpl] against `contracts/commerce.openapi.yaml` (COM-501): every operation the
 * app calls is smoke-called through the real client, checking the request it sends (method, path,
 * query, headers, body), how it reads contract-shaped responses, and how failures are classified. A
 * [MockEngine] stands in for the Commerce service.
 */
class CommerceRepositoryContractTest {

    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")
    private val problemHeaders = headersOf(HttpHeaders.ContentType, "application/problem+json")

    private var lastRequest: HttpRequestData? = null

    @AfterTest
    fun tearDown() = HttpClientProvider.reset()

    private fun serve(status: HttpStatusCode = HttpStatusCode.OK, body: String = "{}"): CommerceRepositoryImpl {
        HttpClientProvider.create(
            MockEngine { request ->
                lastRequest = request
                respond(content = body, status = status, headers = if (status.value < 400) jsonHeaders else problemHeaders)
            },
            authRepository = null,
        )
        return CommerceRepositoryImpl()
    }

    private val request: HttpRequestData get() = lastRequest!!

    private fun requestBody(): String = (request.body as TextContent).text

    private val order = """{"id":"o1","status":"pending","fulfillmentType":"dark_kitchen",""" +
        """"total":{"amount":208.0,"currency":"MXN","formatted":"MXN 208.00"}}"""

    private val createOrder = CreateOrderRequest(
        mealPlanId = "p1",
        fulfillmentType = "dark_kitchen",
        deliveryAddress = OrderAddress(street = "Reforma 222", city = "CDMX", state = "CDMX", zipCode = "06600", country = "MX"),
        deliveryDate = "2026-11-02",
        deliveryTimeSlot = "13:00-14:00",
        paymentMethod = PaymentMethodRequest(type = "credit_card", token = "tok_1"),
    )

    // --- orders ---

    @Test
    fun `creating an order posts the request with its idempotency key and reads the created order`() = runTest {
        val repository = serve(status = HttpStatusCode.Created, body = order)

        val result = repository.createOrder(createOrder, idempotencyKey = "key-1")

        assertEquals(HttpMethod.Post, request.method)
        assertEquals("/commerce/v1/orders", request.url.encodedPath)
        assertEquals("key-1", request.headers["Idempotency-Key"])
        assertEquals(
            """{"mealPlanId":"p1","fulfillmentType":"dark_kitchen","deliveryAddress":{"street":"Reforma 222",""" +
                """"city":"CDMX","state":"CDMX","zipCode":"06600","country":"MX"},"deliveryDate":"2026-11-02",""" +
                """"deliveryTimeSlot":"13:00-14:00","paymentMethod":{"type":"credit_card","token":"tok_1"}}""",
            requestBody(),
        )
        assertEquals("o1", result.id)
        assertEquals("MXN 208.00", result.total?.formatted)
    }

    @Test
    fun `without an idempotency key no header is sent`() = runTest {
        serve(status = HttpStatusCode.Created, body = order).createOrder(createOrder)

        assertNull(request.headers["Idempotency-Key"])
    }

    @Test
    fun `listing orders sends only the filters that are set`() = runTest {
        val repository = serve(body = "[$order]")

        val orders = repository.listOrders(OrderListQuery(status = "pending", limit = 10))

        assertEquals(HttpMethod.Get, request.method)
        assertEquals("/commerce/v1/orders", request.url.encodedPath)
        assertEquals(setOf("status", "limit"), request.url.parameters.names())
        assertEquals("pending", request.url.parameters["status"])
        assertEquals("10", request.url.parameters["limit"])
        assertEquals("o1", orders.single().id)
    }

    @Test
    fun `listing orders without filters sends no query`() = runTest {
        serve(body = "[]").listOrders()

        assertEquals(emptySet(), request.url.parameters.names())
    }

    @Test
    fun `getting an order reads it by id`() = runTest {
        val result = serve(body = order).getOrder("o1")

        assertEquals(HttpMethod.Get, request.method)
        assertEquals("/commerce/v1/orders/o1", request.url.encodedPath)
        assertEquals("pending", result.status)
    }

    @Test
    fun `cancelling without a refund amount sends no body`() = runTest {
        serve(body = order).cancelOrder("o1")

        assertEquals(HttpMethod.Post, request.method)
        assertEquals("/commerce/v1/orders/o1/cancel", request.url.encodedPath)
        assertIs<OutgoingContent.NoContent>(request.body)
    }

    @Test
    fun `cancelling with a partial refund sends the amount`() = runTest {
        serve(body = order).cancelOrder("o1", CancelOrderRequest(refundAmount = 50.0))

        assertEquals("""{"refundAmount":50.0}""", requestBody())
    }

    @Test
    fun `syncing a grocery order posts without a body and reads the order`() = runTest {
        val result = serve(
            body = """{"id":"o1","status":"preparing","groceryOrder":{"providerId":"freshbasket","status":"preparing"}}""",
        ).syncGroceryOrder("o1")

        assertEquals(HttpMethod.Post, request.method)
        assertEquals("/commerce/v1/orders/o1/grocery/sync", request.url.encodedPath)
        assertIs<OutgoingContent.NoContent>(request.body)
        assertEquals("preparing", result.groceryOrder?.status)
    }

    // --- payment methods ---

    @Test
    fun `payment methods are listed`() = runTest {
        val methods = serve(body = """[{"id":"pm1","type":"credit_card","brand":"visa","last4":"4242"}]""")
            .listPaymentMethods()

        assertEquals(HttpMethod.Get, request.method)
        assertEquals("/commerce/v1/payment-methods", request.url.encodedPath)
        assertEquals("4242", methods.single().last4)
    }

    @Test
    fun `saving a payment method posts the token and reads the saved method`() = runTest {
        val saved = serve(status = HttpStatusCode.Created, body = """{"id":"pm1","type":"paypal"}""")
            .savePaymentMethod(SavePaymentMethodRequest(type = "paypal", token = "tok_pp"))

        assertEquals(HttpMethod.Post, request.method)
        assertEquals("/commerce/v1/payment-methods", request.url.encodedPath)
        assertEquals("""{"type":"paypal","token":"tok_pp"}""", requestBody())
        assertEquals("pm1", saved.id)
    }

    @Test
    fun `deleting a payment method accepts the empty 204`() = runTest {
        serve(status = HttpStatusCode.NoContent, body = "").deletePaymentMethod("pm1")

        assertEquals(HttpMethod.Delete, request.method)
        assertEquals("/commerce/v1/payment-methods/pm1", request.url.encodedPath)
    }

    // --- fulfillment ---

    @Test
    fun `kitchen availability is asked for a zip code and an optional date`() = runTest {
        val repository = serve(body = """{"available":true,"zipCode":"06600","timeSlots":["13:00-14:00"]}""")

        val availability = repository.darkKitchenAvailability("06600", deliveryDate = "2026-11-02")

        assertEquals(HttpMethod.Get, request.method)
        assertEquals("/commerce/v1/fulfillment/dark-kitchen/availability", request.url.encodedPath)
        assertEquals("06600", request.url.parameters["zipCode"])
        assertEquals("2026-11-02", request.url.parameters["deliveryDate"])
        assertEquals(listOf("13:00-14:00"), availability.timeSlots)

        repository.darkKitchenAvailability("06600")
        assertEquals(setOf("zipCode"), request.url.parameters.names())
    }

    @Test
    fun `grocery search posts the items and reads the providers`() = runTest {
        val providers = serve(body = """[{"id":"freshbasket","name":"FreshBasket","type":"grocery"}]""")
            .searchGroceryProducts(GrocerySearchRequest(items = listOf(GrocerySearchItem(ingredient = "rice")), zipCode = "06600"))

        assertEquals(HttpMethod.Post, request.method)
        assertEquals("/commerce/v1/fulfillment/grocery/search", request.url.encodedPath)
        assertEquals("""{"items":[{"ingredient":"rice"}],"zipCode":"06600"}""", requestBody())
        assertEquals("FreshBasket", providers.single().name)
    }

    @Test
    fun `grocery providers are listed`() = runTest {
        val providers = serve(body = """[{"id":"walmart","type":"grocery"}]""").groceryProviders()

        assertEquals(HttpMethod.Get, request.method)
        assertEquals("/commerce/v1/fulfillment/grocery/providers", request.url.encodedPath)
        assertEquals("walmart", providers.single().id)
    }

    // --- failures ---

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
                repository.syncGroceryOrder("o1")
            }
            assertEquals(failure, error.toApiFailure(), "status ${status.value}")
        }
    }

    @Test
    fun `a conflict is an HttpError carrying 409`() = runTest {
        val error = assertFailsWith<ApiException.HttpError> {
            serve(status = HttpStatusCode.Conflict, body = """{"type":"about:blank","title":"Conflict","status":409}""")
                .cancelOrder("o1")
        }

        assertEquals(409, error.statusCode)
    }

    @Test
    fun `a failed delete is an HttpError`() = runTest {
        assertFailsWith<ApiException.HttpError> {
            serve(status = HttpStatusCode.NotFound, body = """{"type":"about:blank","title":"x","status":404}""")
                .deletePaymentMethod("pm1")
        }
    }

    @Test
    fun `a reply that does not match the contract is a serialization error`() = runTest {
        // The old client read a bare number total; the contract sends a Money object.
        assertFailsWith<ApiException.SerializationError> {
            serve(body = """{"id":"o1","total":208.0}""").getOrder("o1")
        }
    }

    @Test
    fun `a dropped connection is a network error`() = runTest {
        HttpClientProvider.create(MockEngine { throw IOException("no route to host") }, authRepository = null)

        val error = assertFailsWith<ApiException.NetworkError> { CommerceRepositoryImpl().groceryProviders() }

        assertEquals(ApiFailure.OFFLINE, error.toApiFailure())
    }
}
