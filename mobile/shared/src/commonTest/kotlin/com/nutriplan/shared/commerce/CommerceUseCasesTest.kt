package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.local.OrderStore
import com.nutriplan.shared.data.model.BankTransfer
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
import com.nutriplan.shared.data.model.PaymentApproval
import com.nutriplan.shared.data.model.PaymentMethod
import com.nutriplan.shared.data.model.PaymentMethodRequest
import com.nutriplan.shared.data.model.PaymentVoucher
import com.nutriplan.shared.data.model.SavePaymentMethodRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.repository.CommerceRepository
import com.nutriplan.shared.data.repository.FulfillmentRepository
import com.nutriplan.shared.data.repository.OrderRepository
import com.nutriplan.shared.data.repository.PaymentRepository
import kotlinx.coroutines.flow.last
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * COM-507: the Commerce use cases drive the order, fulfillment and payment flow with validation that
 * mirrors the contract, idempotent retries, and typed results.
 */
class CommerceUseCasesTest {

    /** A Commerce client whose answers each test sets; a [Throwable] answer is thrown. */
    private class FakeCommerce : CommerceRepository {
        var created: Any = order("o1")
        var cancelled: Any = order("o1", "cancelled")
        var savedMethod: Any = PaymentMethod(id = "pm1", type = "credit_card")
        val creates = mutableListOf<Pair<CreateOrderRequest, String?>>()
        val cancels = mutableListOf<Pair<String, CancelOrderRequest?>>()
        val saves = mutableListOf<SavePaymentMethodRequest>()
        val availability = mutableListOf<Pair<String, String?>>()

        @Suppress("UNCHECKED_CAST")
        private fun <T> answer(value: Any): T = if (value is Throwable) throw value else value as T

        override suspend fun createOrder(request: CreateOrderRequest, idempotencyKey: String?): Order {
            creates += request to idempotencyKey
            return answer(created)
        }

        override suspend fun cancelOrder(orderId: String, request: CancelOrderRequest?): Order {
            cancels += orderId to request
            return answer(cancelled)
        }

        override suspend fun savePaymentMethod(request: SavePaymentMethodRequest): PaymentMethod {
            saves += request
            return answer(savedMethod)
        }

        override suspend fun darkKitchenAvailability(zipCode: String, deliveryDate: String?): KitchenAvailability {
            availability += zipCode to deliveryDate
            return KitchenAvailability(available = true, zipCode = zipCode, timeSlots = listOf("13:00-15:00"))
        }

        override suspend fun quoteOrder(request: OrderQuoteRequest): OrderQuote = error("unused")

        override suspend fun listOrders(query: OrderListQuery): List<Order> = listOf(order("o1"))

        override suspend fun getOrder(orderId: String): Order = order(orderId)

        override suspend fun syncGroceryOrder(orderId: String): Order = order(orderId, "preparing")

        override suspend fun listPaymentMethods(): List<PaymentMethod> = emptyList()

        override suspend fun deletePaymentMethod(paymentMethodId: String) = Unit

        override suspend fun searchGroceryProducts(request: GrocerySearchRequest): List<FulfillmentProvider> =
            listOf(FulfillmentProvider(id = "freshbasket"))

        override suspend fun groceryProviders(): List<FulfillmentProvider> = listOf(FulfillmentProvider(id = "freshbasket"))
    }

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

    private val remote = FakeCommerce()
    private val store = MemoryStore()
    private var keys = 0
    private val commerce = CommerceUseCases(
        orders = OrderRepository(remote, store),
        fulfillment = FulfillmentRepository(remote),
        payments = PaymentRepository(remote),
        newIdempotencyKey = { "key-${++keys}" },
    )

    private val offline = ApiException.NetworkError(errorCause = Exception("no route to host"))

    private val address = OrderAddress(street = "Reforma 222", city = "CDMX", state = "CDMX", zipCode = "06600", country = "MX")

    private val draft = CheckoutDraft(
        mealPlanId = "p1",
        fulfillmentType = "dark_kitchen",
        address = address,
        deliveryDate = "2026-11-02",
        deliveryTimeSlot = "13:00-15:00",
    )

    private val card = NewPaymentMethod("credit_card", "tok_visa", brand = "visa", last4 = "4242", expMonth = 12, expYear = 2030)

    // --- validation mirrors the contract ---

    @Test
    fun `a complete draft has no problems`() {
        assertEquals(emptySet(), draft.problems())
        assertEquals(emptySet(), draft.copy(fulfillmentType = "grocery_delivery", providerId = "freshbasket").problems())
        assertEquals(emptySet(), draft.copy(payment = card).problems())
    }

    @Test
    fun `every missing required field is reported`() {
        val empty = CheckoutDraft(
            mealPlanId = " ",
            fulfillmentType = "dark_kitchen",
            address = OrderAddress(street = "", city = " ", state = "", zipCode = "", country = ""),
            deliveryDate = "",
            deliveryTimeSlot = " ",
        )

        assertEquals(
            setOf(
                CheckoutField.MEAL_PLAN,
                CheckoutField.STREET,
                CheckoutField.CITY,
                CheckoutField.STATE,
                CheckoutField.ZIP_CODE,
                CheckoutField.COUNTRY,
                CheckoutField.DELIVERY_DATE,
                CheckoutField.TIME_SLOT,
            ),
            empty.problems(),
        )
    }

    @Test
    fun `values outside the contract are reported`() {
        assertEquals(setOf(CheckoutField.FULFILLMENT_TYPE), draft.copy(fulfillmentType = "drone").problems())
        assertEquals(setOf(CheckoutField.ZIP_CODE), draft.copy(address = address.copy(zipCode = "6600")).problems())
        assertEquals(setOf(CheckoutField.DELIVERY_DATE), draft.copy(deliveryDate = "2026-02-30").problems())
        assertEquals(setOf(CheckoutField.DELIVERY_DATE), draft.copy(deliveryDate = "02/11/2026").problems())
    }

    @Test
    fun `grocery delivery needs a provider`() {
        assertEquals(setOf(CheckoutField.PROVIDER), draft.copy(fulfillmentType = "grocery_delivery").problems())
        assertEquals(setOf(CheckoutField.PROVIDER), draft.copy(fulfillmentType = "grocery_delivery", providerId = " ").problems())
    }

    @Test
    fun `a card number in place of a payment token is a payment problem`() {
        val pan = NewPaymentMethod("credit_card", "4242 4242 4242 4242")

        assertEquals(setOf(CheckoutField.PAYMENT), draft.copy(payment = pan).problems())
        assertEquals(setOf(CheckoutField.PAYMENT), draft.copy(payment = NewPaymentMethod("cash", "tok")).problems())
    }

    @Test
    fun `an invalid draft is rejected without a call`() = runTest {
        assertEquals(OrderResult.Failure(OrderError.REJECTED), commerce.placeOrder(draft.copy(deliveryTimeSlot = "")))
        assertTrue(remote.creates.isEmpty())
    }

    // --- placing an order ---

    @Test
    fun `placing an order sends the trimmed request with its payment and stores the order`() = runTest {
        val messy = draft.copy(
            mealPlanId = " p1 ",
            address = address.copy(street = " Reforma 222 ", apartment = " ", instructions = " Ring twice "),
            payment = NewPaymentMethod("credit_card", " tok_visa "),
            notes = "  ",
        )

        val result = commerce.placeOrder(messy)

        assertEquals(OrderResult.Success(order("o1")), result)
        val (sent, key) = remote.creates.single()
        assertEquals("p1", sent.mealPlanId)
        assertEquals(address.copy(instructions = "Ring twice"), sent.deliveryAddress)
        assertEquals(PaymentMethodRequest(type = "credit_card", token = "tok_visa"), sent.paymentMethod)
        assertEquals(null, sent.notes)
        assertEquals("key-1", key)
        assertEquals(listOf("o1"), store.orders.map { it.id })
    }

    @Test
    fun `a retry of the same checkout reuses its idempotency key`() = runTest {
        remote.created = offline
        assertEquals(OrderResult.Failure(OrderError.NETWORK), commerce.placeOrder(draft))

        remote.created = order("o1")
        commerce.placeOrder(draft)

        assertEquals(listOf<String?>("key-1", "key-1"), remote.creates.map { it.second })
    }

    @Test
    fun `a changed checkout gets a new idempotency key`() = runTest {
        remote.created = offline
        commerce.placeOrder(draft)

        commerce.placeOrder(draft.copy(deliveryTimeSlot = "19:00-21:00"))

        val keys = remote.creates.map { it.second }
        assertEquals(2, keys.toSet().size)
    }

    @Test
    fun `a confirmed order's key is not reused for the next order`() = runTest {
        commerce.placeOrder(draft)
        commerce.placeOrder(draft)

        val keys = remote.creates.map { it.second }
        assertNotEquals(keys[0], keys[1])
    }

    @Test
    fun `the card paid with is saved when asked and the order went through`() = runTest {
        commerce.placeOrder(draft.copy(payment = card, savePaymentMethod = true))

        assertEquals("tok_visa", remote.saves.single().token)
    }

    @Test
    fun `nothing is saved when the order failed or saving was not asked`() = runTest {
        commerce.placeOrder(draft.copy(payment = card))

        remote.created = ApiException.HttpError(statusCode = 402, body = "{}")
        assertEquals(OrderResult.Failure(OrderError.PAYMENT_DECLINED), commerce.placeOrder(draft.copy(payment = card, savePaymentMethod = true)))

        assertTrue(remote.saves.isEmpty())
    }

    @Test
    fun `failing to save the card does not fail the order`() = runTest {
        remote.savedMethod = offline

        val result = commerce.placeOrder(draft.copy(payment = card, savePaymentMethod = true))

        assertEquals(OrderResult.Success(order("o1")), result)
    }

    // --- fulfillment ---

    @Test
    fun `delivery options are asked for the zip code and a valid date`() = runTest {
        assertIs<OrderResult.Success<*>>(commerce.deliveryOptions("06600", deliveryDate = " 2026-11-02 "))
        assertIs<OrderResult.Success<*>>(commerce.deliveryOptions("06600", deliveryDate = ""))

        assertEquals(listOf<Pair<String, String?>>("06600" to "2026-11-02", "06600" to null), remote.availability)
    }

    @Test
    fun `delivery options for an invalid date are rejected without a call`() = runTest {
        assertEquals(OrderResult.Failure(OrderError.REJECTED), commerce.deliveryOptions("06600", deliveryDate = "2026-13-01"))
        assertTrue(remote.availability.isEmpty())
    }

    @Test
    fun `grocery providers and search go through`() = runTest {
        assertIs<OrderResult.Success<*>>(commerce.groceryProviders())
        assertIs<OrderResult.Success<*>>(
            commerce.searchGrocery(listOf(com.nutriplan.shared.data.model.GrocerySearchItem(ingredient = "rice")), "06600"),
        )
    }

    // --- orders ---

    @Test
    fun `orders are read cache-first then refreshed`() = runTest {
        val last = commerce.orders().last() as OrderResult.Success

        assertTrue(last.value.fresh)
        assertEquals(listOf("o1"), last.value.value.map { it.id })
        assertTrue((commerce.order("o2").last() as OrderResult.Success).value.fresh)
    }

    @Test
    fun `a cancellation with a partial refund goes through`() = runTest {
        assertEquals(OrderResult.Success(order("o1", "cancelled")), commerce.cancelOrder(" o1 ", refundAmount = 50.0))
        assertEquals("o1" to CancelOrderRequest(refundAmount = 50.0), remote.cancels.single())
    }

    @Test
    fun `a refund that is not positive is rejected without a call`() = runTest {
        assertEquals(OrderResult.Failure(OrderError.REJECTED), commerce.cancelOrder("o1", refundAmount = 0.0))
        assertEquals(OrderResult.Failure(OrderError.REJECTED), commerce.cancelOrder("o1", refundAmount = -5.0))
        assertEquals(OrderResult.Failure(OrderError.REJECTED), commerce.cancelOrder(" "))
        assertTrue(remote.cancels.isEmpty())
    }

    @Test
    fun `a grocery sync goes through and a blank id is rejected`() = runTest {
        assertEquals(OrderResult.Success(order("o1", "preparing")), commerce.syncGroceryOrder("o1"))
        assertEquals(OrderResult.Failure(OrderError.REJECTED), commerce.syncGroceryOrder(""))
    }

    // --- paying ---

    @Test
    fun `a pending order paid offline says how to pay`() {
        val voucher = PaymentVoucher(reference = "9300 1234")
        val transfer = BankTransfer(clabe = "646180157000000004")
        val approval = PaymentApproval(approvalUrl = "https://paypal.example/a")

        assertEquals(PaymentInstructions.PayAtOxxo(voucher), commerce.paymentInstructions(order("o1").copy(voucher = voucher)))
        assertEquals(PaymentInstructions.TransferWithSpei(transfer), commerce.paymentInstructions(order("o1").copy(transfer = transfer)))
        assertEquals(PaymentInstructions.ApproveWithPayPal(approval), commerce.paymentInstructions(order("o1").copy(approval = approval)))
    }

    @Test
    fun `nothing is left to pay once an order is confirmed or cancelled or has no instructions`() {
        val voucher = PaymentVoucher(reference = "9300 1234")

        assertEquals(PaymentInstructions.None, commerce.paymentInstructions(order("o1", "confirmed").copy(voucher = voucher)))
        assertEquals(PaymentInstructions.None, commerce.paymentInstructions(order("o1", "cancelled").copy(voucher = voucher)))
        assertEquals(PaymentInstructions.None, commerce.paymentInstructions(order("o1")))
    }

    @Test
    fun `saved payment methods go through the payment repository`() = runTest {
        assertEquals(OrderResult.Success(emptyList()), commerce.paymentMethods())
        assertIs<OrderResult.Success<*>>(commerce.addPaymentMethod(card))
        assertEquals(OrderResult.Failure(OrderError.REJECTED), commerce.addPaymentMethod(NewPaymentMethod("credit_card", "4111111111111111")))
        assertEquals(OrderResult.Success(Unit), commerce.deletePaymentMethod("pm1"))
    }

    @Test
    fun `random idempotency keys are long and distinct`() {
        val a = randomIdempotencyKey()
        val b = randomIdempotencyKey()

        assertEquals(32, a.length)
        assertTrue(a.all { it in '0'..'9' || it in 'a'..'f' })
        assertNotEquals(a, b)
    }

    private companion object {
        fun order(id: String, status: String = "pending") = Order(id = id, status = status, fulfillmentType = "dark_kitchen")
    }
}
