package com.nutriplan.shared.contract

import com.nutriplan.shared.commerce.OrderResult
import com.nutriplan.shared.data.local.OrderStore
import com.nutriplan.shared.data.model.CancelOrderRequest
import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.GrocerySearchItem
import com.nutriplan.shared.data.model.GrocerySearchRequest
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderAddress
import com.nutriplan.shared.data.model.OrderListQuery
import com.nutriplan.shared.data.model.PaymentMethodRequest
import com.nutriplan.shared.data.model.SavePaymentMethodRequest
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.CommerceRepositoryImpl
import com.nutriplan.shared.data.repository.FulfillmentRepository
import com.nutriplan.shared.data.repository.OrderRepository
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import kotlinx.coroutines.flow.last
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * Consumer contract tests for the KMP Commerce client (COM-803).
 *
 * The real client the app ships ([CommerceRepositoryImpl], and the typed [OrderRepository] and
 * [FulfillmentRepository] on top of it) is pointed at [SpecDerivedCommerceMock]. Every call must hit
 * a documented operation with documented query and header parameters and a schema-shaped body, and
 * the client must read the spec-shaped reply, every documented field included. A drifted client
 * (renamed field, wrong path or parameter, changed type, a null sent instead of left out) makes a
 * call fail or gets flagged as a contract violation, which fails CI. The mock itself is kept equal to
 * the OpenAPI document by `scripts/check_mobile_commerce_contract.py`; the service's side is held to
 * the same document by its provider contract tests (COM-802).
 */
class CommerceConsumerContractTest {

    private val mock = SpecDerivedCommerceMock()
    private lateinit var commerce: CommerceRepositoryImpl

    @BeforeTest
    fun setUp() {
        HttpClientProvider.create(mock.engine, authRepository = null)
        commerce = CommerceRepositoryImpl()
    }

    @AfterTest
    fun tearDown() = HttpClientProvider.reset()

    private fun assertNoViolations() =
        assertTrue(mock.violations.isEmpty(), "contract violations: ${mock.violations}")

    private fun assertCalled(operation: String) =
        assertTrue(operation in mock.calls, "expected $operation, saw ${mock.calls}")

    private val address = OrderAddress(street = "Reforma 222", city = "CDMX", state = "CDMX", zipCode = "06600", country = "MX")

    private val minimalOrder = CreateOrderRequest(
        mealPlanId = "33333333-3333-4333-8333-333333333333",
        fulfillmentType = "dark_kitchen",
        deliveryAddress = address,
        deliveryDate = "2026-11-02",
        deliveryTimeSlot = "13:00-15:00",
    )

    // --- orders ---

    @Test
    fun `a minimal order conforms and the reply is read in full`() = runTest {
        val order = commerce.createOrder(minimalOrder)

        assertCalled("POST /orders")
        assertNoViolations()
        assertEquals("11111111-1111-4111-8111-111111111111", order.id)
        assertEquals("FreshBasket", order.provider?.name)
        assertEquals(2.0, order.items.single().quantity)
        assertEquals("MXN 178.0", order.items.single().lineTotal?.formatted)
        assertEquals(208.0, order.total?.amount)
        assertEquals("9300 1234", order.voucher?.reference)
        assertEquals("646180157000000004", order.transfer?.clabe)
        assertEquals("https://paypal.example/a", order.approval?.approvalUrl)
        assertEquals("partial", order.refund?.status)
        assertEquals("out_for_delivery", order.groceryOrder?.status)
        assertEquals("https://track.example/o1", order.trackingUrl)
    }

    @Test
    fun `a full order with its idempotency key conforms`() = runTest {
        commerce.createOrder(
            minimalOrder.copy(
                fulfillmentType = "grocery_delivery",
                providerId = "freshbasket",
                deliveryAddress = address.copy(apartment = "4B", instructions = "Ring twice"),
                paymentMethod = PaymentMethodRequest(type = "oxxo", token = "tok_oxxo"),
                notes = "No plastic bags",
            ),
            idempotencyKey = "key-1",
        )

        assertNoViolations()
        assertEquals(
            setOf("mealPlanId", "fulfillmentType", "providerId", "deliveryAddress", "deliveryDate", "deliveryTimeSlot", "paymentMethod", "notes"),
            mock.lastBody?.keys,
        )
    }

    @Test
    fun `listing orders with every filter conforms`() = runTest {
        val orders = commerce.listOrders(OrderListQuery(status = "delivered", fromDate = "2026-10-01", page = 2, limit = 50))

        assertCalled("GET /orders")
        assertNoViolations()
        assertEquals("11111111-1111-4111-8111-111111111111", orders.single().id)
    }

    @Test
    fun `getting and syncing an order conform`() = runTest {
        commerce.getOrder("11111111-1111-4111-8111-111111111111")
        commerce.syncGroceryOrder("11111111-1111-4111-8111-111111111111")

        assertCalled("GET /orders/{orderId}")
        assertCalled("POST /orders/{orderId}/grocery/sync")
        assertNoViolations()
    }

    @Test
    fun `cancelling with and without a refund amount conforms`() = runTest {
        commerce.cancelOrder("11111111-1111-4111-8111-111111111111")
        commerce.cancelOrder("11111111-1111-4111-8111-111111111111", CancelOrderRequest(refundAmount = 50.0))

        assertEquals(2, mock.calls.count { it == "POST /orders/{orderId}/cancel" })
        assertNoViolations()
        assertEquals(setOf("refundAmount"), mock.lastBody?.keys)
    }

    // --- payment methods ---

    @Test
    fun `saving a card and a wallet conforms`() = runTest {
        commerce.savePaymentMethod(SavePaymentMethodRequest("credit_card", "tok_c", brand = "visa", last4 = "4242", expMonth = 12, expYear = 2030))
        val wallet = commerce.savePaymentMethod(SavePaymentMethodRequest("paypal", "tok_pp"))

        assertNoViolations()
        assertEquals(setOf("type", "token"), mock.lastBody?.keys, "a wallet sends no card metadata")
        assertEquals("22222222-2222-4222-8222-222222222222", wallet.id)
    }

    @Test
    fun `listing and deleting payment methods conform`() = runTest {
        val methods = commerce.listPaymentMethods()
        commerce.deletePaymentMethod(methods.single().id)

        assertCalled("GET /payment-methods")
        assertCalled("DELETE /payment-methods/{paymentMethodId}")
        assertNoViolations()
        assertEquals("4242", methods.single().last4)
        assertEquals(2030, methods.single().expYear)
    }

    // --- fulfillment ---

    @Test
    fun `kitchen availability with and without a date conforms`() = runTest {
        val availability = commerce.darkKitchenAvailability("06600", deliveryDate = "2026-11-02")
        commerce.darkKitchenAvailability("06600")

        assertNoViolations()
        assertTrue(availability.available)
        assertEquals(listOf("13:00-15:00", "19:00-21:00"), availability.timeSlots)
    }

    @Test
    fun `grocery providers and search conform`() = runTest {
        val providers = commerce.groceryProviders()
        commerce.searchGroceryProducts(
            GrocerySearchRequest(items = listOf(GrocerySearchItem("rice", 1.0, "kg")), providers = listOf("freshbasket"), zipCode = "06600"),
        )
        commerce.searchGroceryProducts(GrocerySearchRequest(items = listOf(GrocerySearchItem(ingredient = "rice")), zipCode = "06600"))

        assertCalled("GET /fulfillment/grocery/providers")
        assertCalled("POST /fulfillment/grocery/search")
        assertNoViolations()
        assertEquals("Same day, 1-2 h", providers.single().estimatedDelivery)
    }

    // --- the typed repositories on top conform too ---

    private class MemoryStore : OrderStore {
        val orders = mutableListOf<Order>()
        override fun getOrders(status: String?) = orders.filter { status == null || it.status == status }
        override fun getOrder(orderId: String) = orders.firstOrNull { it.id == orderId }
        override fun replaceAll(orders: List<Order>) {
            this.orders.clear()
            this.orders.addAll(orders)
        }
        override fun upsert(order: Order) {
            orders.removeAll { it.id == order.id }
            orders.add(0, order)
        }
        override fun remove(orderId: String) {
            orders.removeAll { it.id == orderId }
        }
    }

    @Test
    fun `the order repository's reads and writes conform`() = runTest {
        val orders = OrderRepository(commerce, MemoryStore())

        assertIs<OrderResult.Success<*>>(orders.orders(status = "pending").last())
        assertIs<OrderResult.Success<*>>(orders.order("11111111-1111-4111-8111-111111111111").last())
        assertIs<OrderResult.Success<*>>(orders.createOrder(minimalOrder, idempotencyKey = "key-2"))
        assertIs<OrderResult.Success<*>>(orders.cancelOrder("11111111-1111-4111-8111-111111111111", refundAmount = 5.0))
        assertIs<OrderResult.Success<*>>(orders.syncGroceryOrder("11111111-1111-4111-8111-111111111111"))
        assertNoViolations()
    }

    @Test
    fun `the fulfillment repository's queries conform`() = runTest {
        val fulfillment = FulfillmentRepository(commerce)

        assertIs<OrderResult.Success<*>>(fulfillment.darkKitchenAvailability(" 06600 "))
        assertIs<OrderResult.Success<*>>(fulfillment.groceryProviders())
        assertIs<OrderResult.Success<*>>(
            fulfillment.searchGrocery(listOf(GrocerySearchItem(ingredient = " rice "), GrocerySearchItem(ingredient = "")), "06600"),
        )
        assertNoViolations()
    }

    // --- the mock catches drift ---

    @Test
    fun `an undocumented operation is a violation`() = runTest {
        val response = HttpClientProvider.client.get("${CommerceContract.clientPrefix}/cart")

        assertEquals(HttpStatusCode.BadRequest, response.status)
        assertTrue(mock.violations.any { it.contains("undocumented operation") })
    }

    @Test
    fun `the old order shape is a violation`() = runTest {
        HttpClientProvider.client.post("${CommerceContract.clientPrefix}/orders") {
            contentType(ContentType.Application.Json)
            setBody("""{"items":[{"recipeId":"r1","quantity":1}],"paymentMethodId":"pm1"}""")
        }

        assertTrue(mock.violations.any { it.contains("missing required") && it.contains("mealPlanId") })
        assertTrue(mock.violations.any { it.contains("undocumented field") && it.contains("paymentMethodId") })
    }

    @Test
    fun `an undocumented address field is a violation`() = runTest {
        HttpClientProvider.client.post("${CommerceContract.clientPrefix}/orders") {
            contentType(ContentType.Application.Json)
            setBody(
                """{"mealPlanId":"p1","fulfillmentType":"pickup","deliveryDate":"2026-11-02","deliveryTimeSlot":"13:00-15:00",""" +
                    """"deliveryAddress":{"line1":"Reforma 222","city":"CDMX","state":"CDMX","postalCode":"06600","country":"MX"}}""",
            )
        }

        assertTrue(mock.violations.any { it.contains("AddressRequest") && it.contains("postalCode") })
    }

    @Test
    fun `a value outside an enum is a violation`() = runTest {
        HttpClientProvider.client.post("${CommerceContract.clientPrefix}/payment-methods") {
            contentType(ContentType.Application.Json)
            setBody("""{"type":"card","token":"tok"}""")
        }

        assertTrue(mock.violations.any { it.contains("type") && it.contains("'card'") })
    }

    @Test
    fun `a field sent as null instead of left out is a violation`() = runTest {
        HttpClientProvider.client.post("${CommerceContract.clientPrefix}/payment-methods") {
            contentType(ContentType.Application.Json)
            setBody("""{"type":"paypal","token":"tok","last4":null}""")
        }

        assertTrue(mock.violations.any { it.contains("sent as null") && it.contains("last4") })
    }

    @Test
    fun `an undocumented search item field is a violation`() = runTest {
        HttpClientProvider.client.post("${CommerceContract.clientPrefix}/fulfillment/grocery/search") {
            contentType(ContentType.Application.Json)
            setBody("""{"items":[{"name":"rice"}],"zipCode":"06600"}""")
        }

        assertTrue(mock.violations.any { it.contains("GrocerySearchRequest.items") && it.contains("name") })
    }

    @Test
    fun `a missing required query parameter is a violation`() = runTest {
        HttpClientProvider.client.get("${CommerceContract.clientPrefix}/fulfillment/dark-kitchen/availability") {
            parameter("postalCode", "06600")
        }

        assertTrue(mock.violations.any { it.contains("missing required query") && it.contains("zipCode") })
        assertTrue(mock.violations.any { it.contains("undocumented query") && it.contains("postalCode") })
    }

    @Test
    fun `an undocumented status filter is a violation`() = runTest {
        HttpClientProvider.client.get("${CommerceContract.clientPrefix}/orders") { parameter("status", "shipped") }

        assertTrue(mock.violations.any { it.contains("status") && it.contains("shipped") })
    }

    @Test
    fun `an idempotency key where it is not documented is a violation`() = runTest {
        HttpClientProvider.client.post("${CommerceContract.clientPrefix}/orders/o1/cancel") { header("Idempotency-Key", "k") }

        assertTrue(mock.violations.any { it.contains("undocumented header") && it.contains("Idempotency-Key") })
    }

    @Test
    fun `a body where the operation takes none is a violation`() = runTest {
        HttpClientProvider.client.post("${CommerceContract.clientPrefix}/orders/o1/grocery/sync") {
            contentType(ContentType.Application.Json)
            setBody("""{"force":true}""")
        }

        assertTrue(mock.violations.any { it.contains("takes no request body") })
    }

    @Test
    fun `every documented operation is exercised by this suite`() {
        assertEquals(
            setOf(
                "POST /orders",
                "GET /orders",
                "GET /orders/{orderId}",
                "POST /orders/{orderId}/cancel",
                "POST /orders/{orderId}/grocery/sync",
                "GET /payment-methods",
                "POST /payment-methods",
                "DELETE /payment-methods/{paymentMethodId}",
                "GET /fulfillment/dark-kitchen/availability",
                "POST /fulfillment/grocery/search",
                "GET /fulfillment/grocery/providers",
            ),
            CommerceContract.operations.map { "${it.method} ${it.path}" }.toSet(),
        )
    }
}
