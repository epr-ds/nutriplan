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
import com.nutriplan.shared.data.repository.CommerceRepository
import com.nutriplan.shared.data.repository.FulfillmentRepository
import com.nutriplan.shared.data.repository.OrderRepository
import com.nutriplan.shared.data.repository.PaymentRepository
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * COM-607: the fulfillment picker behind the checkout step — which way the order is fulfilled
 * (dark kitchen, grocery delivery with a provider, or pickup) and whether it can go through.
 * The shared ViewModel owns the type choice, the dark-kitchen availability and the grocery provider
 * selection, and says whether the user can move on.
 */
class FulfillmentPickerViewModelTest {

    /** A Commerce client whose fulfillment answers each test can set. */
    private class FakeCommerce : CommerceRepository {
        var availability = KitchenAvailability(available = true, zipCode = "06600", timeSlots = listOf("13:00-15:00", "19:00-21:00"))
        var providers = listOf(
            FulfillmentProvider(id = "freshbasket", name = "FreshBasket"),
            FulfillmentProvider(id = "walmart", name = "Walmart"),
        )
        var availabilityCalls = mutableListOf<Pair<String, String?>>()

        override suspend fun darkKitchenAvailability(zipCode: String, deliveryDate: String?): KitchenAvailability {
            availabilityCalls += zipCode to deliveryDate
            return availability
        }

        override suspend fun groceryProviders(): List<FulfillmentProvider> = providers

        override suspend fun quoteOrder(request: OrderQuoteRequest): OrderQuote = error("unused")

        override suspend fun createOrder(request: CreateOrderRequest, idempotencyKey: String?): Order = error("unused")

        override suspend fun listOrders(query: OrderListQuery): List<Order> = emptyList()

        override suspend fun getOrder(orderId: String): Order = error("unused")

        override suspend fun cancelOrder(orderId: String, request: CancelOrderRequest?): Order = error("unused")

        override suspend fun syncGroceryOrder(orderId: String): Order = error("unused")

        override suspend fun listPaymentMethods(): List<PaymentMethod> = emptyList()

        override suspend fun savePaymentMethod(request: SavePaymentMethodRequest): PaymentMethod = error("unused")

        override suspend fun deletePaymentMethod(paymentMethodId: String) = Unit

        override suspend fun searchGroceryProducts(request: GrocerySearchRequest): List<FulfillmentProvider> = emptyList()
    }

    private class MemoryOrders : OrderStore {
        val orders = mutableListOf<Order>()
        override fun getOrders(status: String?): List<Order> = orders.toList()
        override fun getOrder(orderId: String): Order? = orders.firstOrNull { it.id == orderId }
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
    private val orders = MemoryOrders()
    private val useCases = CommerceUseCases(
        orders = OrderRepository(remote, orders),
        fulfillment = FulfillmentRepository(remote),
        payments = PaymentRepository(remote),
    )

    private fun viewModel() = FulfillmentPickerViewModel(useCases = useCases, io = UnconfinedTestDispatcher())

    // --- dark kitchen ---

    @Test
    fun `a dark kitchen delivery can proceed when the area is served`() = runTest {
        val viewModel = viewModel()

        viewModel.start(fulfillmentType = "dark_kitchen", zipCode = "06600", deliveryDate = "2026-11-02")

        val state = viewModel.state.value
        assertEquals("dark_kitchen", state.fulfillmentType)
        assertEquals(true, state.canProceed)
        assertNull(state.error)
    }

    @Test
    fun `a dark kitchen area that is not served cannot proceed`() = runTest {
        remote.availability = KitchenAvailability(available = false, zipCode = "06600", timeSlots = emptyList())

        val viewModel = viewModel()
        viewModel.start(fulfillmentType = "dark_kitchen", zipCode = "06600", deliveryDate = "2026-11-02")

        val state = viewModel.state.value
        assertEquals(false, state.canProceed)
        assertEquals(CheckoutStepError.AREA_NOT_SERVED, state.error)
    }

    // --- grocery delivery ---

    @Test
    fun `a grocery delivery starts without a provider and waits for one`() = runTest {
        val viewModel = viewModel()

        viewModel.start(fulfillmentType = "grocery_delivery", zipCode = "06600")

        val state = viewModel.state.value
        assertEquals("grocery_delivery", state.fulfillmentType)
        val ids: List<String> = state.providers.map { it.id ?: "" }
        assertEquals(listOf("freshbasket", "walmart"), ids)
        assertFalse(state.canProceed, "grocery delivery needs a provider before it can go through")
    }

    @Test
    fun `a grocery provider can complete the delivery`() = runTest {
        val viewModel = viewModel()

        viewModel.start(fulfillmentType = "grocery_delivery", zipCode = "06600")
        viewModel.selectProvider("freshbasket")

        val state = viewModel.state.value
        assertEquals("freshbasket", state.providerId)
        assertTrue(state.canProceed)
    }
}