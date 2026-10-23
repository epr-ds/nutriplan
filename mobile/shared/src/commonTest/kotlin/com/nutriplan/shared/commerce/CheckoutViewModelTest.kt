package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.local.AddressBookStore
import com.nutriplan.shared.data.local.OrderStore
import com.nutriplan.shared.data.local.SavedAddress
import com.nutriplan.shared.data.model.CancelOrderRequest
import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.GrocerySearchRequest
import com.nutriplan.shared.data.model.KitchenAvailability
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.data.model.Money
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderAddress
import com.nutriplan.shared.data.model.OrderItem
import com.nutriplan.shared.data.model.OrderListQuery
import com.nutriplan.shared.data.model.OrderQuote
import com.nutriplan.shared.data.model.OrderQuoteRequest
import com.nutriplan.shared.data.model.PaymentMethod
import com.nutriplan.shared.data.model.PaymentMethodRequest
import com.nutriplan.shared.data.model.PaymentVoucher
import com.nutriplan.shared.data.model.SavePaymentMethodRequest
import com.nutriplan.shared.data.network.ApiException
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
 * COM-605: the checkout stepper -- plan, fulfillment, address, day and slot, review with the quote --
 * validated per step, editable from the review, placing the order through the use cases. COM-608: paying
 * by card through the provider's tokenizer or by OXXO, SPEI or PayPal without a token, and the confirmation.
 */
class CheckoutViewModelTest {

    /** A Commerce client whose fulfillment, quote and order answers each test can set. */
    private class FakeCommerce : CommerceRepository {
        var availability = KitchenAvailability(available = true, zipCode = "06600", timeSlots = listOf("13:00-15:00", "19:00-21:00"))
        var providers = listOf(FulfillmentProvider(id = "freshbasket", name = "FreshBasket"), FulfillmentProvider(id = "walmart", name = "Walmart"))
        var quote = OrderQuote(
            items = listOf(OrderItem(name = "Lentil soup", quantity = 2.0, lineTotal = Money(178.0, formatted = "MXN 178.00"))),
            subtotal = Money(178.0),
            deliveryFee = Money(30.0),
            total = Money(208.0, formatted = "MXN 208.00"),
        )
        var created: Any = Order(id = "o1", status = "pending")
        var quoteFailure: Throwable? = null
        val availabilityCalls = mutableListOf<Pair<String, String?>>()
        val quotes = mutableListOf<OrderQuoteRequest>()
        val creates = mutableListOf<CreateOrderRequest>()
        val idempotencyKeys = mutableListOf<String?>()
        val saves = mutableListOf<SavePaymentMethodRequest>()

        override suspend fun darkKitchenAvailability(zipCode: String, deliveryDate: String?): KitchenAvailability {
            availabilityCalls += zipCode to deliveryDate
            return availability
        }

        override suspend fun groceryProviders(): List<FulfillmentProvider> = providers

        override suspend fun quoteOrder(request: OrderQuoteRequest): OrderQuote {
            quotes += request
            quoteFailure?.let { throw it }
            return quote
        }

        override suspend fun createOrder(request: CreateOrderRequest, idempotencyKey: String?): Order {
            creates += request
            idempotencyKeys += idempotencyKey
            val answer = created
            if (answer is Throwable) throw answer
            return answer as Order
        }

        override suspend fun listOrders(query: OrderListQuery): List<Order> = emptyList()

        override suspend fun getOrder(orderId: String): Order = error("unused")

        override suspend fun cancelOrder(orderId: String, request: CancelOrderRequest?): Order = error("unused")

        override suspend fun syncGroceryOrder(orderId: String): Order = error("unused")

        override suspend fun listPaymentMethods(): List<PaymentMethod> = emptyList()

        override suspend fun savePaymentMethod(request: SavePaymentMethodRequest): PaymentMethod {
            saves += request
            return PaymentMethod(id = "pm1", type = request.type)
        }

        override suspend fun deletePaymentMethod(paymentMethodId: String) = Unit

        override suspend fun searchGroceryProducts(request: GrocerySearchRequest): List<FulfillmentProvider> = emptyList()
    }

    private class MemoryOrders : OrderStore {
        val orders = mutableListOf<Order>()
        override fun getOrders(status: String?) = orders.toList()
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

    private class MemoryAddresses(val saved: MutableList<SavedAddress> = mutableListOf()) : AddressBookStore {
        override fun getAll() = saved.toList()
        override fun save(address: OrderAddress, label: String?, makeDefault: Boolean) =
            SavedAddress(saved.size + 1L, address, label, makeDefault).also { saved.add(0, it) }
        override fun update(id: Long, address: OrderAddress, label: String?, makeDefault: Boolean): SavedAddress? = null
        override fun setDefault(id: Long) = Unit
        override fun remove(id: Long) = Unit
    }

    private val remote = FakeCommerce()
    private val home = SavedAddress(
        id = 1,
        address = OrderAddress(street = "Reforma 222", city = "CDMX", state = "CDMX", zipCode = "06600", country = "MX"),
        label = "Home",
        isDefault = true,
    )
    private val office = home.copy(id = 2, address = home.address.copy(street = "Insurgentes 100", zipCode = "03100"), label = "Office", isDefault = false)
    private val addresses = MemoryAddresses(mutableListOf(home, office))
    private val week = MealPlanSummary(id = "p1", name = "Week 44", startDate = "2026-11-02", endDate = "2026-11-08", status = "active")
    private val other = week.copy(id = "p2", name = "Week 45")
    private var plans: () -> List<MealPlanSummary> = { listOf(week, other) }

    /** The provider's card form: answers with [results] in turn, then with the last one. */
    private class FakeTokenizer(vararg val results: TokenizationResult) : PaymentTokenizer {
        var calls = 0
        override suspend fun tokenize(): TokenizationResult = results[minOf(calls++, results.lastIndex)]
    }

    private val card = NewPaymentMethod(type = "credit_card", token = "tok_visa", brand = "visa", last4 = "4242", expMonth = 12, expYear = 2030)
    private val otherCard = NewPaymentMethod(type = "credit_card", token = "tok_mc", brand = "mastercard", last4 = "4444")

    private fun viewModel(tokenizer: PaymentTokenizer? = null) = CheckoutViewModel(
        useCases = CommerceUseCases(
            orders = OrderRepository(remote, MemoryOrders()),
            fulfillment = FulfillmentRepository(remote),
            payments = PaymentRepository(remote),
        ),
        loadPlans = { plans() },
        addressBook = addresses,
        io = UnconfinedTestDispatcher(),
        tokenizer = tokenizer,
    )

    /** Walk the first steps to [target] with valid choices, paying with [payment] on the review. */
    private suspend fun CheckoutViewModel.walkTo(target: CheckoutStep, type: String = "dark_kitchen", payment: String? = "oxxo") {
        start("2026-11-02")
        selectPlan("p1")
        if (target == CheckoutStep.PLAN) return
        next()
        selectFulfillment(type)
        if (type == "grocery_delivery") selectProvider("freshbasket")
        if (target == CheckoutStep.FULFILLMENT) return
        next()
        if (target == CheckoutStep.ADDRESS) return
        next()
        if (target == CheckoutStep.SLOT) return
        selectSlot(state.value.slots.first())
        next()
        payment?.let { selectPayment(it) }
    }

    // --- start ---

    @Test
    fun `starting loads the plans and addresses and preselects the default address`() = runTest {
        val viewModel = viewModel()

        viewModel.start("2026-11-02")

        val state = viewModel.state.value
        assertFalse(state.plansLoading)
        assertEquals(listOf("p1", "p2"), state.plans.map { it.id })
        assertNull(state.planId, "with several plans nothing is chosen for the user")
        assertEquals(home.id, state.addressId)
        assertEquals("2026-11-02", state.deliveryDate)
        assertEquals(CheckoutStep.PLAN, state.step)
    }

    @Test
    fun `a single plan or the one asked for is preselected`() = runTest {
        plans = { listOf(week) }
        val single = viewModel()
        single.start("2026-11-02")
        assertEquals("p1", single.state.value.planId)

        plans = { listOf(week, other) }
        val asked = viewModel()
        asked.start("2026-11-02", planId = "p2")
        assertEquals("p2", asked.state.value.planId)
    }

    @Test
    fun `plans that cannot be loaded are an error`() = runTest {
        plans = { throw ApiException.NetworkError(errorCause = Exception("offline")) }
        val viewModel = viewModel()

        viewModel.start("2026-11-02")

        assertEquals(OrderError.NETWORK, viewModel.state.value.error)
        assertFalse(viewModel.state.value.plansLoading)
    }

    @Test
    fun `a rejected session asks the user to sign in again`() = runTest {
        plans = { throw ApiException.HttpError(statusCode = 401, body = "{}") }
        val viewModel = viewModel()

        viewModel.start("2026-11-02")

        assertTrue(viewModel.state.value.sessionExpired)
    }

    // --- validation per step ---

    @Test
    fun `each step needs its choice before moving on`() = runTest {
        val viewModel = viewModel()
        viewModel.start("2026-11-02")

        assertFalse(viewModel.next())
        assertEquals(CheckoutStepError.PLAN_REQUIRED, viewModel.state.value.stepError)

        viewModel.selectPlan("p1")
        assertTrue(viewModel.next())
        assertFalse(viewModel.next())
        assertEquals(CheckoutStepError.FULFILLMENT_REQUIRED, viewModel.state.value.stepError)
    }

    @Test
    fun `grocery delivery lists the stores and needs one`() = runTest {
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.PLAN)
        viewModel.next()

        viewModel.selectFulfillment("grocery_delivery")

        assertEquals(listOf("freshbasket", "walmart"), viewModel.state.value.providers.map { it.id })
        assertFalse(viewModel.next())
        assertEquals(CheckoutStepError.PROVIDER_REQUIRED, viewModel.state.value.stepError)
        viewModel.selectProvider("walmart")
        assertTrue(viewModel.next())
    }

    @Test
    fun `a single store is chosen for the user`() = runTest {
        remote.providers = listOf(FulfillmentProvider(id = "freshbasket"))
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.PLAN)
        viewModel.next()

        viewModel.selectFulfillment("grocery_delivery")

        assertEquals("freshbasket", viewModel.state.value.providerId)
    }

    @Test
    fun `an address is required`() = runTest {
        addresses.saved.clear()
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.ADDRESS)

        assertFalse(viewModel.next())
        assertEquals(CheckoutStepError.ADDRESS_REQUIRED, viewModel.state.value.stepError)
    }

    @Test
    fun `an address added meanwhile is picked up`() = runTest {
        addresses.saved.clear()
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.ADDRESS)

        addresses.saved += home
        viewModel.refreshAddresses()

        assertEquals(home.id, viewModel.state.value.addressId)
        assertTrue(viewModel.next())
    }

    // --- day and slot ---

    @Test
    fun `a dark kitchen offers its slots for the address and day`() = runTest {
        val viewModel = viewModel()

        viewModel.walkTo(CheckoutStep.SLOT)

        assertEquals(listOf<Pair<String, String?>>("06600" to "2026-11-02"), remote.availabilityCalls)
        assertEquals(listOf("13:00-15:00", "19:00-21:00"), viewModel.state.value.slots)
    }

    @Test
    fun `a slot is required`() = runTest {
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.SLOT)

        assertFalse(viewModel.next())
        assertEquals(CheckoutStepError.SLOT_REQUIRED, viewModel.state.value.stepError)
    }

    @Test
    fun `an area the kitchen does not serve cannot be chosen`() = runTest {
        remote.availability = KitchenAvailability(available = false, zipCode = "06600")
        val viewModel = viewModel()

        viewModel.walkTo(CheckoutStep.SLOT)

        assertEquals(CheckoutStepError.AREA_NOT_SERVED, viewModel.state.value.stepError)
        assertTrue(viewModel.state.value.slots.isEmpty())
        assertFalse(viewModel.next())
    }

    @Test
    fun `changing the day looks the slots up again`() = runTest {
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.SLOT)
        viewModel.selectSlot("13:00-15:00")

        viewModel.onDateChange("2026-11-03")

        assertNull(viewModel.state.value.timeSlot)
        assertEquals("2026-11-03", remote.availabilityCalls.last().second)
    }

    @Test
    fun `grocery delivery and pickup offer the standard windows`() = runTest {
        val viewModel = viewModel()

        viewModel.walkTo(CheckoutStep.SLOT, type = "pickup")

        assertEquals(CheckoutViewModel.STANDARD_TIME_SLOTS, viewModel.state.value.slots)
        assertTrue(remote.availabilityCalls.isEmpty())
    }

    // --- review ---

    @Test
    fun `the review shows the itemized price for the choices`() = runTest {
        val viewModel = viewModel()

        viewModel.walkTo(CheckoutStep.REVIEW, type = "grocery_delivery")

        assertEquals(CheckoutStep.REVIEW, viewModel.state.value.step)
        assertEquals(OrderQuoteRequest("p1", "grocery_delivery", "freshbasket"), remote.quotes.single())
        assertEquals("MXN 208.00", viewModel.state.value.quote?.total?.formatted)
    }

    @Test
    fun `a price that cannot be loaded is an error to retry`() = runTest {
        remote.quoteFailure = ApiException.HttpError(statusCode = 503, body = "{}")
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.REVIEW)

        assertEquals(OrderError.SERVER_PROBLEM, viewModel.state.value.error)
        remote.quoteFailure = null
        viewModel.loadQuote()

        assertNull(viewModel.state.value.error)
        assertEquals(208.0, viewModel.state.value.quote?.total?.amount)
    }

    @Test
    fun `any earlier step can be edited from the review`() = runTest {
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.REVIEW)

        viewModel.edit(CheckoutStep.ADDRESS)
        assertEquals(CheckoutStep.ADDRESS, viewModel.state.value.step)
        viewModel.selectAddress(office.id)
        viewModel.next()

        assertNull(viewModel.state.value.timeSlot, "a new address needs a new slot")
        assertEquals("03100", remote.availabilityCalls.last().first)
    }

    @Test
    fun `a later step cannot be jumped to`() = runTest {
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.PLAN)

        viewModel.edit(CheckoutStep.REVIEW)

        assertEquals(CheckoutStep.PLAN, viewModel.state.value.step)
    }

    @Test
    fun `back goes one step back and not past the first`() = runTest {
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.FULFILLMENT)

        assertTrue(viewModel.back())
        assertEquals(CheckoutStep.PLAN, viewModel.state.value.step)
        assertFalse(viewModel.back())
    }

    @Test
    fun `changing how it is received clears the slot and the price`() = runTest {
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.REVIEW)

        viewModel.edit(CheckoutStep.FULFILLMENT)
        viewModel.selectFulfillment("pickup")

        assertNull(viewModel.state.value.timeSlot)
        assertNull(viewModel.state.value.quote)
    }

    // --- placing the order ---

    @Test
    fun `the reviewed order is placed with every choice`() = runTest {
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.REVIEW)

        assertTrue(viewModel.placeOrder())

        val sent = remote.creates.single()
        assertEquals("p1", sent.mealPlanId)
        assertEquals("dark_kitchen", sent.fulfillmentType)
        assertEquals(home.address, sent.deliveryAddress)
        assertEquals("2026-11-02", sent.deliveryDate)
        assertEquals("13:00-15:00", sent.deliveryTimeSlot)
        assertNull(sent.providerId)
        assertEquals(PaymentMethodRequest(type = "oxxo"), sent.paymentMethod)
        assertEquals("o1", viewModel.state.value.placedOrderId)
    }

    @Test
    fun `an order that is not placed says why and can be placed again`() = runTest {
        remote.created = ApiException.HttpError(statusCode = 409, body = "{}")
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.REVIEW)

        assertFalse(viewModel.placeOrder())
        assertEquals(OrderError.CONFLICT, viewModel.state.value.error)

        remote.created = Order(id = "o2", status = "pending")
        assertTrue(viewModel.placeOrder())
        assertEquals("o2", viewModel.state.value.placedOrderId)
    }

    @Test
    fun `an incomplete checkout is never placed`() = runTest {
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.ADDRESS)

        assertFalse(viewModel.placeOrder())
        assertTrue(remote.creates.isEmpty())
    }

    // --- paying (COM-608) ---

    @Test
    fun `an order needs a way to pay`() = runTest {
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.REVIEW, payment = null)

        assertFalse(viewModel.placeOrder())

        assertEquals(CheckoutStepError.PAYMENT_REQUIRED, viewModel.state.value.stepError)
        assertTrue(remote.creates.isEmpty())
        viewModel.selectPayment("spei")
        assertNull(viewModel.state.value.stepError)
    }

    @Test
    fun `a card is not offered without the provider card form`() = runTest {
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.REVIEW, payment = null)

        viewModel.selectPayment("credit_card")

        assertFalse(viewModel.state.value.canPayByCard)
        assertNull(viewModel.state.value.paymentType)
        assertTrue(viewModel(FakeTokenizer(TokenizationResult.Cancelled)).state.value.canPayByCard)
    }

    @Test
    fun `an unknown way to pay is ignored`() = runTest {
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.REVIEW)

        viewModel.selectPayment("bitcoin")

        assertEquals("oxxo", viewModel.state.value.paymentType)
    }

    @Test
    fun `OXXO SPEI and PayPal are placed without a token`() = runTest {
        for (type in listOf("oxxo", "spei", "paypal")) {
            remote.creates.clear()
            val viewModel = viewModel()
            viewModel.walkTo(CheckoutStep.REVIEW, payment = type)

            assertTrue(viewModel.placeOrder())

            assertEquals(PaymentMethodRequest(type = type), remote.creates.single().paymentMethod)
        }
        assertTrue(remote.saves.isEmpty())
    }

    @Test
    fun `a card is tokenized when the order is placed and only the token is sent`() = runTest {
        val tokenizer = FakeTokenizer(TokenizationResult.Tokenized(card))
        val viewModel = viewModel(tokenizer)
        viewModel.walkTo(CheckoutStep.REVIEW, payment = "credit_card")
        assertEquals(0, tokenizer.calls, "the card form opens only when the user places the order")

        assertTrue(viewModel.placeOrder())

        assertEquals(1, tokenizer.calls)
        assertEquals(PaymentMethodRequest(type = "credit_card", token = "tok_visa"), remote.creates.single().paymentMethod)
        assertTrue(remote.saves.isEmpty(), "the card is not saved unless the user asks")
    }

    @Test
    fun `a card the user wants kept is saved with the order`() = runTest {
        val viewModel = viewModel(FakeTokenizer(TokenizationResult.Tokenized(card)))
        viewModel.walkTo(CheckoutStep.REVIEW, payment = "credit_card")
        viewModel.onSaveCardChange(true)

        assertTrue(viewModel.placeOrder())

        val saved = remote.saves.single()
        assertEquals("tok_visa", saved.token)
        assertEquals("4242", saved.last4)
    }

    @Test
    fun `save card only applies to a card`() = runTest {
        val viewModel = viewModel(FakeTokenizer(TokenizationResult.Tokenized(card)))
        viewModel.walkTo(CheckoutStep.REVIEW, payment = "oxxo")
        viewModel.onSaveCardChange(true)

        assertTrue(viewModel.placeOrder())

        assertTrue(remote.saves.isEmpty())
    }

    @Test
    fun `closing the card form places nothing and shows no error`() = runTest {
        val viewModel = viewModel(FakeTokenizer(TokenizationResult.Cancelled))
        viewModel.walkTo(CheckoutStep.REVIEW, payment = "credit_card")

        assertFalse(viewModel.placeOrder())

        assertTrue(remote.creates.isEmpty())
        assertFalse(viewModel.state.value.isPlacing)
        assertNull(viewModel.state.value.stepError)
        assertNull(viewModel.state.value.error)
    }

    @Test
    fun `a card the provider cannot verify says so`() = runTest {
        val viewModel = viewModel(FakeTokenizer(TokenizationResult.Failed))
        viewModel.walkTo(CheckoutStep.REVIEW, payment = "credit_card")

        assertFalse(viewModel.placeOrder())

        assertEquals(CheckoutStepError.CARD_NOT_VERIFIED, viewModel.state.value.stepError)
        assertTrue(remote.creates.isEmpty())
        assertFalse(viewModel.state.value.isPlacing)
    }

    @Test
    fun `a retry after a network failure reuses the card and the idempotency key`() = runTest {
        remote.created = ApiException.NetworkError(errorCause = Exception("offline"))
        val tokenizer = FakeTokenizer(TokenizationResult.Tokenized(card), TokenizationResult.Tokenized(otherCard))
        val viewModel = viewModel(tokenizer)
        viewModel.walkTo(CheckoutStep.REVIEW, payment = "credit_card")

        assertFalse(viewModel.placeOrder())
        assertEquals(OrderError.NETWORK, viewModel.state.value.error)
        remote.created = Order(id = "o1", status = "paid")
        assertTrue(viewModel.placeOrder())

        assertEquals(1, tokenizer.calls, "the card is not tokenized (or charged) twice")
        assertEquals(2, remote.creates.size)
        assertEquals(remote.creates[0], remote.creates[1])
        assertEquals(remote.idempotencyKeys[0], remote.idempotencyKeys[1])
    }

    @Test
    fun `a declined card asks for a card again`() = runTest {
        remote.created = ApiException.HttpError(statusCode = 402, body = "{}")
        val tokenizer = FakeTokenizer(TokenizationResult.Tokenized(card), TokenizationResult.Tokenized(otherCard))
        val viewModel = viewModel(tokenizer)
        viewModel.walkTo(CheckoutStep.REVIEW, payment = "credit_card")

        assertFalse(viewModel.placeOrder())
        assertEquals(OrderError.PAYMENT_DECLINED, viewModel.state.value.error)
        remote.created = Order(id = "o1", status = "paid")
        assertTrue(viewModel.placeOrder())

        assertEquals(2, tokenizer.calls)
        assertEquals("tok_mc", remote.creates.last().paymentMethod?.token)
    }

    @Test
    fun `switching away from a card forgets the tokenized card`() = runTest {
        remote.created = ApiException.NetworkError(errorCause = Exception("offline"))
        val tokenizer = FakeTokenizer(TokenizationResult.Tokenized(card), TokenizationResult.Tokenized(otherCard))
        val viewModel = viewModel(tokenizer)
        viewModel.walkTo(CheckoutStep.REVIEW, payment = "credit_card")
        assertFalse(viewModel.placeOrder())

        viewModel.selectPayment("oxxo")
        viewModel.selectPayment("credit_card")
        remote.created = Order(id = "o1", status = "paid")
        assertTrue(viewModel.placeOrder())

        assertEquals(2, tokenizer.calls)
    }

    @Test
    fun `the confirmation keeps the placed order and what is left to pay`() = runTest {
        val voucher = PaymentVoucher(reference = "93000012345678", amount = Money(208.0, formatted = "MXN 208.00"), expiresAt = "2026-11-01T23:59:00Z")
        remote.created = Order(id = "o1", status = "pending", total = Money(208.0, formatted = "MXN 208.00"), voucher = voucher)
        val viewModel = viewModel()
        viewModel.walkTo(CheckoutStep.REVIEW)

        assertTrue(viewModel.placeOrder())

        val state = viewModel.state.value
        assertEquals("o1", state.placedOrder?.id)
        assertEquals(PaymentInstructions.PayAtOxxo(voucher), state.paymentInstructions)
        assertFalse(state.isPlacing)
    }

    @Test
    fun `a paid order has nothing left to pay`() = runTest {
        remote.created = Order(id = "o1", status = "paid")
        val viewModel = viewModel(FakeTokenizer(TokenizationResult.Tokenized(card)))
        viewModel.walkTo(CheckoutStep.REVIEW, payment = "credit_card")

        assertTrue(viewModel.placeOrder())

        assertEquals(PaymentInstructions.None, viewModel.state.value.paymentInstructions)
    }
}
