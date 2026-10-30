package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.local.OrderStore
import com.nutriplan.shared.data.model.CancelOrderRequest
import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.GrocerySearchRequest
import com.nutriplan.shared.data.model.KitchenAvailability
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderListQuery
import com.nutriplan.shared.data.model.OrderQuote
import com.nutriplan.shared.data.model.OrderQuoteRequest
import com.nutriplan.shared.data.model.PaymentMethod
import com.nutriplan.shared.data.model.SavePaymentMethodRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.repository.CommerceRepository
import com.nutriplan.shared.data.repository.FulfillmentRepository
import com.nutriplan.shared.data.repository.OrderRepository
import com.nutriplan.shared.data.repository.PaymentRepository
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * COM-701: the order list -- cache-first then refreshed, filtered by status, with loading, empty and
 * error states and a reorder action.
 */
class OrderListViewModelTest {

    /** A Commerce client whose order list each test can set, or make fail. */
    private class FakeCommerce : CommerceRepository {
        var orders: List<Order> = emptyList()
        var failure: Throwable? = null
        val queries = mutableListOf<OrderListQuery>()

        override suspend fun listOrders(query: OrderListQuery): List<Order> {
            queries += query
            failure?.let { throw it }
            return orders
        }

        override suspend fun createOrder(request: CreateOrderRequest, idempotencyKey: String?): Order = error("unused")
        override suspend fun quoteOrder(request: OrderQuoteRequest): OrderQuote = error("unused")
        override suspend fun getOrder(orderId: String): Order = error("unused")
        override suspend fun cancelOrder(orderId: String, request: CancelOrderRequest?): Order = error("unused")
        override suspend fun syncGroceryOrder(orderId: String): Order = error("unused")
        override suspend fun listPaymentMethods(): List<PaymentMethod> = emptyList()
        override suspend fun savePaymentMethod(request: SavePaymentMethodRequest): PaymentMethod = error("unused")
        override suspend fun deletePaymentMethod(paymentMethodId: String) = Unit
        override suspend fun darkKitchenAvailability(zipCode: String, deliveryDate: String?): KitchenAvailability = error("unused")
        override suspend fun groceryProviders(): List<FulfillmentProvider> = emptyList()
        override suspend fun searchGroceryProducts(request: GrocerySearchRequest): List<FulfillmentProvider> = emptyList()
    }

    private class MemoryOrders : OrderStore {
        val orders = mutableListOf<Order>()
        override fun getOrders(status: String?) = orders.filter { status == null || it.status == status }
        override fun getOrder(orderId: String) = orders.firstOrNull { it.id == orderId }
        override fun replaceAll(orders: List<Order>) {
            this.orders.clear()
            this.orders.addAll(orders)
        }
        override fun upsert(order: Order) {
            orders.add(0, order)
        }
        override fun remove(orderId: String) {
            orders.removeAll { it.id == orderId }
        }
    }

    private val remote = FakeCommerce()
    private val store = MemoryOrders()

    private val pending = Order(id = "o1", status = "pending", fulfillmentType = "dark_kitchen")
    private val onItsWay = Order(id = "o2", status = "in_transit", fulfillmentType = "grocery_delivery")
    private val delivered = Order(id = "o3", status = "delivered", fulfillmentType = "pickup")
    private val cancelled = Order(id = "o4", status = "cancelled", fulfillmentType = "dark_kitchen")
    private val all = listOf(pending, onItsWay, delivered, cancelled)

    private fun viewModel() = OrderListViewModel(
        CommerceUseCases(
            orders = OrderRepository(remote, store),
            fulfillment = FulfillmentRepository(remote),
            payments = PaymentRepository(remote),
        ),
    )

    @Test
    fun `the orders are loaded newest first from the server`() = runTest {
        remote.orders = all
        val viewModel = viewModel()

        viewModel.load()

        val state = viewModel.state.value
        assertFalse(state.isLoading)
        assertEquals(listOf("o1", "o2", "o3", "o4"), state.visibleOrders.map { it.id })
        assertNull(state.refreshError)
        assertNull(remote.queries.single().status, "every order is read and filtered on the device")
    }

    @Test
    fun `before loading the list is loading`() {
        assertTrue(viewModel().state.value.isLoading)
    }

    @Test
    fun `no orders is the empty state`() = runTest {
        val viewModel = viewModel()

        viewModel.load()

        assertTrue(viewModel.state.value.isEmpty)
        assertFalse(viewModel.state.value.isFilteredEmpty)
    }

    @Test
    fun `each filter shows only its statuses`() = runTest {
        remote.orders = all
        val viewModel = viewModel()
        viewModel.load()

        viewModel.selectFilter(OrderFilter.ACTIVE)
        assertEquals(listOf("o1", "o2"), viewModel.state.value.visibleOrders.map { it.id })
        viewModel.selectFilter(OrderFilter.DELIVERED)
        assertEquals(listOf("o3"), viewModel.state.value.visibleOrders.map { it.id })
        viewModel.selectFilter(OrderFilter.CANCELLED)
        assertEquals(listOf("o4"), viewModel.state.value.visibleOrders.map { it.id })
        viewModel.selectFilter(OrderFilter.ALL)
        assertEquals(4, viewModel.state.value.visibleOrders.size)
    }

    @Test
    fun `each filter counts its orders`() = runTest {
        remote.orders = all + Order(id = "o5", status = "confirmed")
        val viewModel = viewModel()
        viewModel.load()

        val state = viewModel.state.value
        assertEquals(5, state.count(OrderFilter.ALL))
        assertEquals(3, state.count(OrderFilter.ACTIVE))
        assertEquals(1, state.count(OrderFilter.DELIVERED))
        assertEquals(1, state.count(OrderFilter.CANCELLED))
    }

    @Test
    fun `a filter with no orders says so without being the empty state`() = runTest {
        remote.orders = listOf(pending)
        val viewModel = viewModel()
        viewModel.load()

        viewModel.selectFilter(OrderFilter.DELIVERED)

        assertTrue(viewModel.state.value.isFilteredEmpty)
        assertFalse(viewModel.state.value.isEmpty)
    }

    @Test
    fun `offline the saved orders stay on screen with the reason`() = runTest {
        store.orders += listOf(pending, delivered)
        remote.failure = ApiException.NetworkError(errorCause = Exception("offline"))
        val viewModel = viewModel()

        viewModel.load()

        val state = viewModel.state.value
        assertFalse(state.isLoading)
        assertEquals(listOf("o1", "o3"), state.visibleOrders.map { it.id })
        assertEquals(OrderError.NETWORK, state.refreshError)
        assertNull(state.loadError)
    }

    @Test
    fun `offline with nothing saved is an error to retry`() = runTest {
        remote.failure = ApiException.NetworkError(errorCause = Exception("offline"))
        val viewModel = viewModel()

        viewModel.load()
        assertEquals(OrderError.NETWORK, viewModel.state.value.loadError)
        assertFalse(viewModel.state.value.isEmpty, "a failure is not an empty list")

        remote.failure = null
        remote.orders = listOf(pending)
        viewModel.load()

        assertNull(viewModel.state.value.loadError)
        assertEquals(listOf("o1"), viewModel.state.value.visibleOrders.map { it.id })
    }

    @Test
    fun `a rejected session asks the user to sign in again`() = runTest {
        remote.failure = ApiException.HttpError(statusCode = 401, body = "{}")
        val viewModel = viewModel()

        viewModel.load()

        assertTrue(viewModel.state.value.sessionExpired)
    }

    @Test
    fun `the server's list replaces the saved one`() = runTest {
        store.orders += listOf(cancelled)
        remote.orders = listOf(pending)
        val viewModel = viewModel()

        viewModel.load()

        assertEquals(listOf("o1"), viewModel.state.value.visibleOrders.map { it.id })
        assertNull(viewModel.state.value.refreshError)
    }

    @Test
    fun `the current state is the latest one`() = runTest {
        val viewModel = viewModel()

        assertTrue(viewModel.state.value.isLoading)

        remote.orders = all
        viewModel.load()

        assertEquals(listOf("o1", "o2", "o3", "o4"), viewModel.currentState().visibleOrders.map { it.id })
    }

    @Test
    fun `refresh reloads the orders`() = runTest {
        remote.orders = all
        val viewModel = viewModel()
        viewModel.load()

        assertEquals(listOf("o1", "o2", "o3", "o4"), viewModel.state.value.visibleOrders.map { it.id })
        viewModel.refresh()

        assertEquals(2, remote.queries.size, "the refresh reads the list again")
    }

    @Test
    fun `an order the checkout offers can be reordered`() {
        val viewModel = viewModel()

        assertTrue(viewModel.canReorder(pending))
        assertTrue(viewModel.canReorder(onItsWay))
        assertTrue(viewModel.canReorder(delivered))
        assertFalse(viewModel.canReorder(Order(id = "o9", status = "delivered")))
        assertFalse(viewModel.canReorder(Order(id = "o9", fulfillmentType = "drone")))
    }
}
