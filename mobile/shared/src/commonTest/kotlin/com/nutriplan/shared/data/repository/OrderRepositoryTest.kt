package com.nutriplan.shared.data.repository

import com.nutriplan.shared.commerce.Fetched
import com.nutriplan.shared.commerce.OrderError
import com.nutriplan.shared.commerce.OrderResult
import com.nutriplan.shared.data.local.OrderStore
import com.nutriplan.shared.data.model.CancelOrderRequest
import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.GrocerySearchRequest
import com.nutriplan.shared.data.model.KitchenAvailability
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderAddress
import com.nutriplan.shared.data.model.OrderListQuery
import com.nutriplan.shared.data.model.OrderQuote
import com.nutriplan.shared.data.model.OrderQuoteRequest
import com.nutriplan.shared.data.model.PaymentMethod
import com.nutriplan.shared.data.model.SavePaymentMethodRequest
import com.nutriplan.shared.data.network.ApiException
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import kotlin.coroutines.cancellation.CancellationException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * COM-504: the offline-first order repository -- reads emit the device's copy and then the server's
 * answer, writes go through to the server and are stored, and every outcome is a typed result.
 */
class OrderRepositoryTest {

    /** An in-memory [OrderStore] with the same ordering rules as the device's cache. */
    private class MemoryStore(orders: List<Order> = emptyList()) : OrderStore {
        val orders = orders.toMutableList()

        override fun getOrders(status: String?) = orders.filter { status == null || it.status == status }

        override fun getOrder(orderId: String) = orders.firstOrNull { it.id == orderId }

        override fun replaceAll(orders: List<Order>) {
            this.orders.clear()
            this.orders.addAll(orders)
        }

        override fun upsert(order: Order) {
            val index = orders.indexOfFirst { it.id == order.id }
            if (index >= 0) orders[index] = order else orders.add(0, order)
        }

        override fun remove(orderId: String) {
            orders.removeAll { it.id == orderId }
        }
    }

    /** A Commerce client whose answers each test sets; a [Throwable] answer is thrown. */
    private class FakeCommerce : CommerceRepository {
        var list: Any = emptyList<Order>()
        var detail: Any = order("o1")
        var write: Any = order("o1")
        val queries = mutableListOf<OrderListQuery>()
        val idempotencyKeys = mutableListOf<String?>()
        val cancellations = mutableListOf<Pair<String, CancelOrderRequest?>>()

        @Suppress("UNCHECKED_CAST")
        private fun <T> answer(value: Any): T = if (value is Throwable) throw value else value as T

        override suspend fun quoteOrder(request: OrderQuoteRequest): OrderQuote = error("unused")

        override suspend fun listOrders(query: OrderListQuery): List<Order> {
            queries += query
            return answer(list)
        }

        override suspend fun getOrder(orderId: String): Order = answer(detail)

        override suspend fun createOrder(request: CreateOrderRequest, idempotencyKey: String?): Order {
            idempotencyKeys += idempotencyKey
            return answer(write)
        }

        override suspend fun cancelOrder(orderId: String, request: CancelOrderRequest?): Order {
            cancellations += orderId to request
            return answer(write)
        }

        override suspend fun syncGroceryOrder(orderId: String): Order = answer(write)

        override suspend fun listPaymentMethods(): List<PaymentMethod> = emptyList()

        override suspend fun savePaymentMethod(request: SavePaymentMethodRequest): PaymentMethod = error("unused")

        override suspend fun deletePaymentMethod(paymentMethodId: String) = Unit

        override suspend fun darkKitchenAvailability(zipCode: String, deliveryDate: String?): KitchenAvailability =
            error("unused")

        override suspend fun searchGroceryProducts(request: GrocerySearchRequest): List<FulfillmentProvider> = emptyList()

        override suspend fun groceryProviders(): List<FulfillmentProvider> = emptyList()
    }

    private val remote = FakeCommerce()

    private fun repository(vararg cached: Order) = MemoryStore(cached.toList()).let { it to OrderRepository(remote, it) }

    private val offline = ApiException.NetworkError(errorCause = Exception("no route to host"))
    private fun http(status: Int) = ApiException.HttpError(statusCode = status, body = """{"status":$status}""")

    private val request = CreateOrderRequest(
        mealPlanId = "p1",
        fulfillmentType = "dark_kitchen",
        deliveryAddress = OrderAddress(street = "Reforma 222", city = "CDMX", state = "CDMX", zipCode = "06600", country = "MX"),
        deliveryDate = "2026-11-02",
        deliveryTimeSlot = "13:00-15:00",
    )

    private fun <T> OrderResult<Fetched<T>>.fetched(): Fetched<T> = (this as OrderResult.Success).value

    // --- orders(): cache-first, then refresh ---

    @Test
    fun `with nothing cached the server's orders are the only answer and are stored`() = runTest {
        remote.list = listOf(order("o2"), order("o1"))
        val (store, orders) = repository()

        val emitted = orders.orders().toList()

        assertEquals(1, emitted.size)
        assertEquals(Fetched(listOf(order("o2"), order("o1")), fresh = true), emitted.single().fetched())
        assertEquals(listOf("o2", "o1"), store.orders.map { it.id })
    }

    @Test
    fun `the cached orders come first and then the server's which replace them`() = runTest {
        remote.list = listOf(order("o3"), order("o2"))
        val (store, orders) = repository(order("o2"), order("o1"))

        val emitted = orders.orders().toList()

        assertEquals(listOf("o2", "o1"), emitted[0].fetched().value.map { it.id })
        assertEquals(false, emitted[0].fetched().fresh)
        assertEquals(listOf("o3", "o2"), emitted[1].fetched().value.map { it.id })
        assertTrue(emitted[1].fetched().fresh)
        assertEquals(listOf("o3", "o2"), store.orders.map { it.id }, "an order the server no longer lists is dropped")
    }

    @Test
    fun `asks the server for the largest page and the status`() = runTest {
        val (_, orders) = repository()

        orders.orders(status = "pending").toList()

        assertEquals(OrderListQuery(status = "pending", limit = 100), remote.queries.single())
    }

    @Test
    fun `offline the cached orders stay with the reason they are not fresh`() = runTest {
        remote.list = offline
        val (_, orders) = repository(order("o1"))

        val last = orders.orders().toList().last().fetched()

        assertEquals(listOf("o1"), last.value.map { it.id })
        assertEquals(false, last.fresh)
        assertEquals(OrderError.NETWORK, last.refreshError)
    }

    @Test
    fun `a server failure with a copy keeps the copy`() = runTest {
        remote.list = http(503)
        val (_, orders) = repository(order("o1"))

        assertEquals(OrderError.SERVER_PROBLEM, orders.orders().toList().last().fetched().refreshError)
    }

    @Test
    fun `offline with nothing cached is a failure`() = runTest {
        remote.list = offline
        val (_, orders) = repository()

        assertEquals(listOf<OrderResult<*>>(OrderResult.Failure(OrderError.NETWORK)), orders.orders().toList())
    }

    @Test
    fun `a rejected session is a failure even with a copy`() = runTest {
        remote.list = http(401)
        val (_, orders) = repository(order("o1"))

        assertEquals(OrderResult.Failure(OrderError.SESSION_EXPIRED), orders.orders().toList().last())
    }

    @Test
    fun `a status refresh drops that status's orders the server no longer lists and keeps the others`() = runTest {
        remote.list = listOf(order("o3", "pending"))
        val (store, orders) = repository(order("o3", "pending"), order("o2", "pending"), order("o1", "delivered"))

        val emitted = orders.orders(status = "pending").toList()

        assertEquals(listOf("o3", "o2"), emitted.first().fetched().value.map { it.id }, "only that status is shown")
        assertEquals(listOf("o3", "o1"), store.orders.map { it.id })
    }

    @Test
    fun `a full page does not drop older cached orders that may be on the next page`() = runTest {
        remote.list = (100 downTo 1).map { order("n$it") }
        val (store, orders) = repository(order("old"))

        orders.orders().toList()

        assertEquals(101, store.orders.size)
        assertEquals("n100", store.orders.first().id, "the newest is in front")
        assertTrue(store.orders.any { it.id == "old" })
    }

    // --- order(): cache-first, then refresh ---

    @Test
    fun `one order comes from the cache first and then from the server which refreshes it`() = runTest {
        remote.detail = order("o1", "confirmed")
        val (store, orders) = repository(order("o1", "pending"))

        val emitted = orders.order("o1").toList()

        assertEquals(Fetched(order("o1", "pending"), fresh = false), emitted[0].fetched())
        assertEquals(Fetched(order("o1", "confirmed"), fresh = true), emitted[1].fetched())
        assertEquals("confirmed", store.getOrder("o1")?.status)
    }

    @Test
    fun `an order the server no longer has is forgotten`() = runTest {
        remote.detail = http(404)
        val (store, orders) = repository(order("o1"))

        assertEquals(OrderResult.Failure(OrderError.NOT_FOUND), orders.order("o1").toList().last())
        assertNull(store.getOrder("o1"))
    }

    @Test
    fun `offline the cached order stays`() = runTest {
        remote.detail = offline
        val (_, orders) = repository(order("o1"))

        val last = orders.order("o1").toList().last().fetched()

        assertEquals(order("o1"), last.value)
        assertEquals(OrderError.NETWORK, last.refreshError)
    }

    @Test
    fun `offline with the order not cached is a failure`() = runTest {
        remote.detail = offline
        val (_, orders) = repository()

        assertEquals(listOf<OrderResult<*>>(OrderResult.Failure(OrderError.NETWORK)), orders.order("o1").toList())
    }

    // --- writes go through ---

    @Test
    fun `a created order is stored in front and the idempotency key is sent`() = runTest {
        remote.write = order("new")
        val (store, orders) = repository(order("o1"))

        val result = orders.createOrder(request, idempotencyKey = "key-1")

        assertEquals(OrderResult.Success(order("new")), result)
        assertEquals(listOf("new", "o1"), store.orders.map { it.id })
        assertEquals(listOf<String?>("key-1"), remote.idempotencyKeys)
    }

    @Test
    fun `a declined card stores nothing`() = runTest {
        remote.write = http(402)
        val (store, orders) = repository()

        assertEquals(OrderResult.Failure(OrderError.PAYMENT_DECLINED), orders.createOrder(request))
        assertTrue(store.orders.isEmpty())
    }

    @Test
    fun `creating an order offline is a failure and never a fake order`() = runTest {
        remote.write = offline
        val (store, orders) = repository()

        assertEquals(OrderResult.Failure(OrderError.NETWORK), orders.createOrder(request))
        assertTrue(store.orders.isEmpty())
    }

    @Test
    fun `a cancellation refreshes the cached order in place`() = runTest {
        remote.write = order("o2", "cancelled")
        val (store, orders) = repository(order("o3"), order("o2"), order("o1"))

        val result = orders.cancelOrder("o2", refundAmount = 50.0)

        assertEquals(OrderResult.Success(order("o2", "cancelled")), result)
        assertEquals(listOf("o3", "o2", "o1"), store.orders.map { it.id })
        assertEquals("cancelled", store.getOrder("o2")?.status)
        assertEquals("o2" to CancelOrderRequest(refundAmount = 50.0), remote.cancellations.single())
    }

    @Test
    fun `cancelling without a refund amount sends no body`() = runTest {
        remote.write = order("o1", "cancelled")
        val (_, orders) = repository(order("o1"))

        orders.cancelOrder("o1")

        assertEquals("o1" to null, remote.cancellations.single())
    }

    @Test
    fun `an order that can no longer be cancelled is a conflict and stays as it was`() = runTest {
        remote.write = http(409)
        val (store, orders) = repository(order("o1", "delivered"))

        assertEquals(OrderResult.Failure(OrderError.CONFLICT), orders.cancelOrder("o1"))
        assertEquals("delivered", store.getOrder("o1")?.status)
    }

    @Test
    fun `a refund over the total is rejected`() = runTest {
        remote.write = http(422)
        val (_, orders) = repository(order("o1"))

        assertEquals(OrderResult.Failure(OrderError.REJECTED), orders.cancelOrder("o1", refundAmount = 9999.0))
    }

    @Test
    fun `cancelling an order the server no longer has forgets it`() = runTest {
        remote.write = http(404)
        val (store, orders) = repository(order("o1"))

        assertEquals(OrderResult.Failure(OrderError.NOT_FOUND), orders.cancelOrder("o1"))
        assertNull(store.getOrder("o1"))
    }

    @Test
    fun `a grocery sync stores the order the provider reported`() = runTest {
        remote.write = order("o1", "preparing")
        val (store, orders) = repository(order("o1", "confirmed"))

        assertEquals(OrderResult.Success(order("o1", "preparing")), orders.syncGroceryOrder("o1"))
        assertEquals("preparing", store.getOrder("o1")?.status)
    }

    @Test
    fun `a provider outage during a sync is a server problem`() = runTest {
        remote.write = http(503)
        val (_, orders) = repository(order("o1"))

        assertEquals(OrderResult.Failure(OrderError.SERVER_PROBLEM), orders.syncGroceryOrder("o1"))
    }

    @Test
    fun `cancellation of the caller is never swallowed`() = runTest {
        remote.write = CancellationException("left the screen")
        val (_, orders) = repository()

        assertFailsWith<CancellationException> { orders.createOrder(request) }
    }

    private companion object {
        fun order(id: String, status: String = "pending") = Order(id = id, status = status, fulfillmentType = "dark_kitchen")
    }
}
