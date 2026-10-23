package com.nutriplan.shared.data.repository

import com.nutriplan.shared.commerce.OrderError
import com.nutriplan.shared.commerce.OrderResult
import com.nutriplan.shared.data.model.CancelOrderRequest
import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.GrocerySearchItem
import com.nutriplan.shared.data.model.GrocerySearchRequest
import com.nutriplan.shared.data.model.KitchenAvailability
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderListQuery
import com.nutriplan.shared.data.model.OrderQuote
import com.nutriplan.shared.data.model.OrderQuoteRequest
import com.nutriplan.shared.data.model.PaymentMethod
import com.nutriplan.shared.data.model.SavePaymentMethodRequest
import com.nutriplan.shared.data.network.ApiException
import kotlinx.coroutines.test.runTest
import kotlin.coroutines.cancellation.CancellationException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * COM-505: the fulfillment queries return typed results with the same error mapping as orders, and
 * input the server would refuse anyway is refused without a call.
 */
class FulfillmentRepositoryTest {

    /** A Commerce client whose fulfillment answers each test sets; a [Throwable] answer is thrown. */
    private class FakeCommerce : CommerceRepository {
        var availability: Any = KitchenAvailability(available = true, zipCode = "06600", timeSlots = listOf("13:00-15:00"))
        var providers: Any = listOf(FulfillmentProvider(id = "freshbasket", name = "FreshBasket", type = "grocery"))
        var search: Any = listOf(FulfillmentProvider(id = "freshbasket", type = "grocery"))
        val availabilityCalls = mutableListOf<Pair<String, String?>>()
        val searches = mutableListOf<GrocerySearchRequest>()
        var providerCalls = 0

        @Suppress("UNCHECKED_CAST")
        private fun <T> answer(value: Any): T = if (value is Throwable) throw value else value as T

        override suspend fun darkKitchenAvailability(zipCode: String, deliveryDate: String?): KitchenAvailability {
            availabilityCalls += zipCode to deliveryDate
            return answer(availability)
        }

        override suspend fun groceryProviders(): List<FulfillmentProvider> {
            providerCalls++
            return answer(providers)
        }

        override suspend fun searchGroceryProducts(request: GrocerySearchRequest): List<FulfillmentProvider> {
            searches += request
            return answer(search)
        }

        override suspend fun createOrder(request: CreateOrderRequest, idempotencyKey: String?): Order = error("unused")

        override suspend fun quoteOrder(request: OrderQuoteRequest): OrderQuote = error("unused")

        override suspend fun listOrders(query: OrderListQuery): List<Order> = error("unused")

        override suspend fun getOrder(orderId: String): Order = error("unused")

        override suspend fun cancelOrder(orderId: String, request: CancelOrderRequest?): Order = error("unused")

        override suspend fun syncGroceryOrder(orderId: String): Order = error("unused")

        override suspend fun listPaymentMethods(): List<PaymentMethod> = error("unused")

        override suspend fun savePaymentMethod(request: SavePaymentMethodRequest): PaymentMethod = error("unused")

        override suspend fun deletePaymentMethod(paymentMethodId: String) = error("unused")
    }

    private val remote = FakeCommerce()
    private val fulfillment = FulfillmentRepository(remote)

    private val offline = ApiException.NetworkError(errorCause = Exception("no route to host"))
    private fun http(status: Int) = ApiException.HttpError(statusCode = status, body = """{"status":$status}""")

    // --- dark-kitchen availability ---

    @Test
    fun `availability for a served zip code is a success with its time slots`() = runTest {
        val result = fulfillment.darkKitchenAvailability("06600", deliveryDate = "2026-11-02")

        val availability = (result as OrderResult.Success).value
        assertTrue(availability.available)
        assertEquals(listOf("13:00-15:00"), availability.timeSlots)
        assertEquals(listOf<Pair<String, String?>>("06600" to "2026-11-02"), remote.availabilityCalls)
    }

    @Test
    fun `an area the kitchen does not serve is a success saying so`() = runTest {
        remote.availability = KitchenAvailability(available = false, zipCode = "99999")

        val result = fulfillment.darkKitchenAvailability("99999")

        assertEquals(OrderResult.Success(KitchenAvailability(available = false, zipCode = "99999")), result)
    }

    @Test
    fun `the zip code and date are trimmed and a blank date is left out`() = runTest {
        fulfillment.darkKitchenAvailability(" 06600 ", deliveryDate = "  ")

        assertEquals(listOf<Pair<String, String?>>("06600" to null), remote.availabilityCalls)
    }

    @Test
    fun `a zip code that is not five digits is rejected without a call`() = runTest {
        listOf("", "0660", "066000", "06a00").forEach { zip ->
            assertEquals(OrderResult.Failure(OrderError.REJECTED), fulfillment.darkKitchenAvailability(zip), zip)
        }
        assertTrue(remote.availabilityCalls.isEmpty())
    }

    @Test
    fun `availability failures are typed`() = runTest {
        val expected = mapOf(
            offline to OrderError.NETWORK,
            http(401) to OrderError.SESSION_EXPIRED,
            http(422) to OrderError.REJECTED,
            http(503) to OrderError.SERVER_PROBLEM,
        )

        expected.forEach { (failure, error) ->
            remote.availability = failure
            assertEquals(OrderResult.Failure(error), fulfillment.darkKitchenAvailability("06600"), error.name)
        }
    }

    // --- grocery providers ---

    @Test
    fun `the grocery providers are listed`() = runTest {
        val result = fulfillment.groceryProviders()

        assertEquals("FreshBasket", (result as OrderResult.Success).value.single().name)
    }

    @Test
    fun `no providers is an empty success`() = runTest {
        remote.providers = emptyList<FulfillmentProvider>()

        assertEquals(OrderResult.Success(emptyList()), fulfillment.groceryProviders())
    }

    @Test
    fun `providers are always asked of the server`() = runTest {
        fulfillment.groceryProviders()
        fulfillment.groceryProviders()

        assertEquals(2, remote.providerCalls)
    }

    @Test
    fun `listing providers offline is a network failure`() = runTest {
        remote.providers = offline

        assertEquals(OrderResult.Failure(OrderError.NETWORK), fulfillment.groceryProviders())
    }

    // --- grocery search ---

    @Test
    fun `a search sends the ingredients and the zip code and returns the providers that have them`() = runTest {
        val result = fulfillment.searchGrocery(
            items = listOf(GrocerySearchItem(ingredient = "rice", quantity = 1.0, unit = "kg")),
            zipCode = "06600",
        )

        assertEquals("freshbasket", (result as OrderResult.Success).value.single().id)
        val sent = remote.searches.single()
        assertEquals(listOf(GrocerySearchItem(ingredient = "rice", quantity = 1.0, unit = "kg")), sent.items)
        assertEquals("06600", sent.zipCode)
        assertNull(sent.providers, "every provider when none is named")
    }

    @Test
    fun `ingredient names are trimmed and lines without one are dropped`() = runTest {
        fulfillment.searchGrocery(
            items = listOf(
                GrocerySearchItem(ingredient = "  rice "),
                GrocerySearchItem(ingredient = "   "),
                GrocerySearchItem(ingredient = null, quantity = 2.0),
                GrocerySearchItem(ingredient = "chicken", quantity = 500.0, unit = "g"),
            ),
            zipCode = "06600",
        )

        assertEquals(
            listOf(GrocerySearchItem(ingredient = "rice"), GrocerySearchItem(ingredient = "chicken", quantity = 500.0, unit = "g")),
            remote.searches.single().items,
        )
    }

    @Test
    fun `the search can be limited to named providers`() = runTest {
        fulfillment.searchGrocery(
            items = listOf(GrocerySearchItem(ingredient = "rice")),
            zipCode = "06600",
            providers = listOf(" walmart ", "", "freshbasket", "walmart"),
        )

        assertEquals(listOf("walmart", "freshbasket"), remote.searches.single().providers)
    }

    @Test
    fun `a search with nothing to look for is rejected without a call`() = runTest {
        assertEquals(OrderResult.Failure(OrderError.REJECTED), fulfillment.searchGrocery(emptyList(), "06600"))
        assertEquals(
            OrderResult.Failure(OrderError.REJECTED),
            fulfillment.searchGrocery(listOf(GrocerySearchItem(ingredient = " ")), "06600"),
        )
        assertTrue(remote.searches.isEmpty())
    }

    @Test
    fun `a search with a bad zip code is rejected without a call`() = runTest {
        val result = fulfillment.searchGrocery(listOf(GrocerySearchItem(ingredient = "rice")), "6600")

        assertEquals(OrderResult.Failure(OrderError.REJECTED), result)
        assertTrue(remote.searches.isEmpty())
    }

    @Test
    fun `no provider having the ingredients is an empty success`() = runTest {
        remote.search = emptyList<FulfillmentProvider>()

        val result = fulfillment.searchGrocery(listOf(GrocerySearchItem(ingredient = "saffron")), "06600")

        assertEquals(OrderResult.Success(emptyList()), result)
    }

    @Test
    fun `search failures are typed`() = runTest {
        val expected = mapOf(
            offline to OrderError.NETWORK,
            http(401) to OrderError.SESSION_EXPIRED,
            http(422) to OrderError.REJECTED,
            http(500) to OrderError.SERVER_PROBLEM,
            ApiException.SerializationError() to OrderError.UNKNOWN,
        )

        expected.forEach { (failure, error) ->
            remote.search = failure
            val result = fulfillment.searchGrocery(listOf(GrocerySearchItem(ingredient = "rice")), "06600")
            assertEquals(OrderResult.Failure(error), result, error.name)
        }
    }

    @Test
    fun `cancellation of the caller is never swallowed`() = runTest {
        remote.providers = CancellationException("left the screen")

        assertFailsWith<CancellationException> { fulfillment.groceryProviders() }
    }
}
