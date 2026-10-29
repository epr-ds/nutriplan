package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.local.OrderStore
import com.nutriplan.shared.data.model.CancelOrderRequest
import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.GrocerySearchRequest
import com.nutriplan.shared.data.model.KitchenAvailability
import com.nutriplan.shared.data.model.Money
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderListQuery
import com.nutriplan.shared.data.model.OrderQuote
import com.nutriplan.shared.data.model.OrderQuoteRequest
import com.nutriplan.shared.data.model.OrderStatusChange
import com.nutriplan.shared.data.model.PaymentMethod
import com.nutriplan.shared.data.model.PaymentVoucher
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
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * COM-703: one order's detail -- cache-first then refreshed, its status timeline, and cancelling
 * it (after confirming) while it has not been dispatched.
 */
class OrderDetailViewModelTest {

    /** A Commerce client whose order and cancellation answers each test can set. */
    private class FakeCommerce : CommerceRepository {
        var order: Any = Order(id = "o1", status = "confirmed")
        var cancelled: Any = Order(id = "o1", status = "cancelled")
        val cancels = mutableListOf<String>()

        override suspend fun getOrder(orderId: String): Order {
            val answer = order
            if (answer is Throwable) throw answer
            return answer as Order
        }

        override suspend fun cancelOrder(orderId: String, request: CancelOrderRequest?): Order {
            cancels += orderId
            val answer = cancelled
            if (answer is Throwable) throw answer
            return answer as Order
        }

        override suspend fun listOrders(query: OrderListQuery): List<Order> = emptyList()
        override suspend fun createOrder(request: CreateOrderRequest, idempotencyKey: String?): Order = error("unused")
        override suspend fun quoteOrder(request: OrderQuoteRequest): OrderQuote = error("unused")
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
            orders.removeAll { it.id == order.id }
            orders.add(0, order)
        }
        override fun remove(orderId: String) {
            orders.removeAll { it.id == orderId }
        }
    }

    private val remote = FakeCommerce()
    private val store = MemoryOrders()

    private fun viewModel() = OrderDetailViewModel(
        CommerceUseCases(
            orders = OrderRepository(remote, store),
            fulfillment = FulfillmentRepository(remote),
            payments = PaymentRepository(remote),
        ),
    )

    private val placedAt = "2026-10-23T18:00:00Z"
    private val confirmedAt = "2026-10-23T18:05:00Z"
    private val preparingAt = "2026-10-23T19:00:00Z"
    private val history = listOf(
        OrderStatusChange("pending", "confirmed", confirmedAt),
        OrderStatusChange("confirmed", "preparing", preparingAt),
    )

    // --- the timeline ---

    @Test
    fun `the timeline marks the steps done before the current one`() {
        val order = Order(id = "o1", status = "preparing", createdAt = placedAt, statusHistory = history)

        assertEquals(
            listOf(
                TimelineStep("pending", placedAt, TimelineStepState.DONE),
                TimelineStep("confirmed", confirmedAt, TimelineStepState.DONE),
                TimelineStep("preparing", preparingAt, TimelineStepState.CURRENT),
                TimelineStep("in_transit", null, TimelineStepState.UPCOMING),
                TimelineStep("delivered", null, TimelineStepState.UPCOMING),
            ),
            order.timeline(),
        )
    }

    @Test
    fun `a new order is at its first step`() {
        val steps = Order(id = "o1", status = "pending", createdAt = placedAt).timeline()

        assertEquals(TimelineStep("pending", placedAt, TimelineStepState.CURRENT), steps.first())
        assertTrue(steps.drop(1).all { it.state == TimelineStepState.UPCOMING })
    }

    @Test
    fun `a delivered order has every step reached`() {
        val delivered = history + listOf(
            OrderStatusChange("preparing", "in_transit", "2026-10-23T20:00:00Z"),
            OrderStatusChange("in_transit", "delivered", "2026-10-23T20:40:00Z"),
        )
        val steps = Order(id = "o1", status = "delivered", createdAt = placedAt, statusHistory = delivered).timeline()

        assertEquals(TimelineStepState.CURRENT, steps.last().state)
        assertEquals("2026-10-23T20:40:00Z", steps.last().reachedAt)
        assertTrue(steps.dropLast(1).all { it.state == TimelineStepState.DONE })
    }

    @Test
    fun `a cancelled order shows the steps it went through and then the cancellation`() {
        val cancelledAt = "2026-10-23T18:30:00Z"
        val order = Order(
            id = "o1",
            status = "cancelled",
            createdAt = placedAt,
            statusHistory = listOf(history.first(), OrderStatusChange("confirmed", "cancelled", cancelledAt)),
        )

        assertEquals(
            listOf(
                TimelineStep("pending", placedAt, TimelineStepState.DONE),
                TimelineStep("confirmed", confirmedAt, TimelineStepState.DONE),
                TimelineStep("cancelled", cancelledAt, TimelineStepState.CURRENT),
            ),
            order.timeline(),
        )
    }

    @Test
    fun `a cancelled order without history still ends with the cancellation`() {
        val steps = Order(id = "o1", status = "cancelled").timeline()

        assertEquals(listOf("pending", "cancelled"), steps.map { it.status })
        assertEquals(TimelineStepState.CURRENT, steps.last().state)
    }

    @Test
    fun `an order is cancellable only until it is dispatched`() {
        assertTrue(Order(id = "o1", status = "pending").canCancel)
        assertTrue(Order(id = "o1", status = "confirmed").canCancel)
        assertTrue(Order(id = "o1", status = "preparing").canCancel)
        assertFalse(Order(id = "o1", status = "in_transit").canCancel)
        assertFalse(Order(id = "o1", status = "delivered").canCancel)
        assertFalse(Order(id = "o1", status = "cancelled").canCancel)
    }

    // --- loading ---

    @Test
    fun `the current state is the latest one`() = runTest {
        val viewModel = viewModel()

        assertTrue(viewModel.state.value.isLoading)

        remote.order = Order(id = "o1", status = "preparing", createdAt = placedAt, statusHistory = history)
        viewModel.load("o1")

        assertEquals("preparing", viewModel.currentState().order?.status)
    }

    @Test
    fun `the order is loaded from the server`() = runTest {
        remote.order = Order(id = "o1", status = "preparing", createdAt = placedAt, statusHistory = history)
        val viewModel = viewModel()

        viewModel.load("o1")

        val state = viewModel.state.value
        assertFalse(state.isLoading)
        assertEquals("preparing", state.order?.status)
        assertEquals(TimelineStepState.CURRENT, state.timeline[2].state)
        assertTrue(state.canCancel)
    }

    @Test
    fun `offline the saved copy stays on screen with the reason`() = runTest {
        store.orders += Order(id = "o1", status = "confirmed")
        remote.order = ApiException.NetworkError(errorCause = Exception("offline"))
        val viewModel = viewModel()

        viewModel.load("o1")

        assertEquals("confirmed", viewModel.state.value.order?.status)
        assertEquals(OrderError.NETWORK, viewModel.state.value.refreshError)
        assertFalse(viewModel.state.value.isLoading)
    }

    @Test
    fun `an order the server no longer has is not found`() = runTest {
        remote.order = ApiException.HttpError(statusCode = 404, body = "{}")
        val viewModel = viewModel()

        viewModel.load("o1")

        assertEquals(OrderError.NOT_FOUND, viewModel.state.value.loadError)
        assertNull(viewModel.state.value.order)
    }

    @Test
    fun `a rejected session asks the user to sign in again`() = runTest {
        remote.order = ApiException.HttpError(statusCode = 401, body = "{}")
        val viewModel = viewModel()

        viewModel.load("o1")

        assertTrue(viewModel.state.value.sessionExpired)
    }

    @Test
    fun `a pending OXXO order shows what is left to pay`() = runTest {
        val voucher = PaymentVoucher(reference = "9300 1234", amount = Money(208.0))
        remote.order = Order(id = "o1", status = "pending", voucher = voucher)
        val viewModel = viewModel()

        viewModel.load("o1")

        assertEquals(PaymentInstructions.PayAtOxxo(voucher), viewModel.state.value.paymentInstructions)
    }

    // --- cancelling ---

    @Test
    fun `cancelling asks first and then cancels`() = runTest {
        val viewModel = viewModel()
        viewModel.load("o1")

        viewModel.requestCancel()
        assertTrue(viewModel.state.value.confirmingCancel)
        assertTrue(remote.cancels.isEmpty(), "nothing is cancelled before the user confirms")

        assertTrue(viewModel.confirmCancel())

        assertEquals(listOf("o1"), remote.cancels)
        assertEquals("cancelled", viewModel.state.value.order?.status)
        assertFalse(viewModel.state.value.confirmingCancel)
        assertFalse(viewModel.state.value.canCancel)
        assertEquals("cancelled", store.getOrder("o1")?.status, "the saved copy is updated too")
    }

    @Test
    fun `keeping the order cancels nothing`() = runTest {
        val viewModel = viewModel()
        viewModel.load("o1")

        viewModel.requestCancel()
        viewModel.dismissCancel()

        assertFalse(viewModel.state.value.confirmingCancel)
        assertTrue(remote.cancels.isEmpty())
    }

    @Test
    fun `a dispatched order offers no cancel`() = runTest {
        remote.order = Order(id = "o1", status = "in_transit")
        val viewModel = viewModel()
        viewModel.load("o1")

        viewModel.requestCancel()

        assertFalse(viewModel.state.value.canCancel)
        assertFalse(viewModel.state.value.confirmingCancel)
    }

    @Test
    fun `an order dispatched meanwhile says so and shows where it is now`() = runTest {
        remote.cancelled = ApiException.HttpError(statusCode = 409, body = "{}")
        val viewModel = viewModel()
        viewModel.load("o1")
        remote.order = Order(id = "o1", status = "in_transit")

        viewModel.requestCancel()
        assertFalse(viewModel.confirmCancel())

        assertEquals(OrderError.CONFLICT, viewModel.state.value.cancelError)
        assertEquals("in_transit", viewModel.state.value.order?.status)
        assertFalse(viewModel.state.value.canCancel)
    }

    @Test
    fun `a cancellation that fails offline can be tried again`() = runTest {
        remote.cancelled = ApiException.NetworkError(errorCause = Exception("offline"))
        val viewModel = viewModel()
        viewModel.load("o1")

        viewModel.requestCancel()
        assertFalse(viewModel.confirmCancel())
        assertEquals(OrderError.NETWORK, viewModel.state.value.cancelError)
        assertTrue(viewModel.state.value.canCancel)

        remote.cancelled = Order(id = "o1", status = "cancelled")
        viewModel.dismissCancelError()
        viewModel.requestCancel()
        assertTrue(viewModel.confirmCancel())

        assertNull(viewModel.state.value.cancelError)
        assertIs<Order>(viewModel.state.value.order)
        assertEquals("cancelled", viewModel.state.value.order?.status)
    }
}
