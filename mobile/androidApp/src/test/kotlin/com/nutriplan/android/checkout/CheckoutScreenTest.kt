package com.nutriplan.android.checkout

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.screen.checkout.CheckoutScreenContent
import com.nutriplan.android.screen.checkout.CheckoutTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.commerce.CheckoutStep
import com.nutriplan.shared.commerce.CheckoutViewModel
import com.nutriplan.shared.commerce.CommerceUseCases
import com.nutriplan.shared.commerce.NewPaymentMethod
import com.nutriplan.shared.commerce.PaymentTokenizer
import com.nutriplan.shared.commerce.TokenizationResult
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
import com.nutriplan.shared.data.repository.CommerceRepository
import com.nutriplan.shared.data.repository.FulfillmentRepository
import com.nutriplan.shared.data.repository.OrderRepository
import com.nutriplan.shared.data.repository.PaymentRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * COM-605: the checkout stepper walks plan -> fulfillment -> address -> day and slot -> review with
 * the itemized price, checks each step, lets the user edit any step from the review, and places
 * the order. COM-608: the review asks how to pay (a card only with the provider's card form), and
 * the placed order shows a confirmation with what is left to pay. Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
// A tall viewport so every lazily composed item is on screen.
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2400dp", application = TestApplication::class)
class CheckoutScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private class FakeCommerce : CommerceRepository {
        val creates = mutableListOf<CreateOrderRequest>()
        val saves = mutableListOf<SavePaymentMethodRequest>()
        val quotes = mutableListOf<OrderQuoteRequest>()
        var created = Order(id = "o1", status = "pending")

        override suspend fun quoteOrder(request: OrderQuoteRequest): OrderQuote {
            quotes += request
            return OrderQuote(
                items = listOf(OrderItem(name = "Lentil soup", quantity = 2.0, lineTotal = Money(178.0, formatted = "MXN 178.00"))),
                subtotal = Money(178.0, formatted = "MXN 178.00"),
                deliveryFee = Money(0.0, formatted = "MXN 0.00"),
                total = Money(178.0, formatted = "MXN 178.00"),
            )
        }

        override suspend fun createOrder(request: CreateOrderRequest, idempotencyKey: String?): Order {
            creates += request
            return created
        }

        override suspend fun darkKitchenAvailability(zipCode: String, deliveryDate: String?) =
            KitchenAvailability(available = true, zipCode = zipCode, timeSlots = listOf("13:00-15:00"))
        override suspend fun groceryProviders(): List<FulfillmentProvider> = listOf(FulfillmentProvider(id = "freshbasket", name = "FreshBasket"))
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

    private class NoOrders : OrderStore {
        override fun getOrders(status: String?) = emptyList<Order>()
        override fun getOrder(orderId: String): Order? = null
        override fun replaceAll(orders: List<Order>) = Unit
        override fun upsert(order: Order) = Unit
        override fun remove(orderId: String) = Unit
    }

    private class Addresses(val saved: List<SavedAddress>) : AddressBookStore {
        override fun getAll() = saved
        override fun save(address: OrderAddress, label: String?, makeDefault: Boolean) = error("unused")
        override fun update(id: Long, address: OrderAddress, label: String?, makeDefault: Boolean): SavedAddress? = null
        override fun setDefault(id: Long) = Unit
        override fun remove(id: Long) = Unit
    }

    /** The provider's card form, answering [result]. */
    private class FakeTokenizer(val result: TokenizationResult) : PaymentTokenizer {
        override suspend fun tokenize() = result
    }

    private val card = NewPaymentMethod(type = "credit_card", token = "tok_visa", brand = "visa", last4 = "4242")

    private val remote = FakeCommerce()
    private val home = SavedAddress(
        id = 1,
        address = OrderAddress(street = "Reforma 222", city = "CDMX", state = "CDMX", zipCode = "06600", country = "MX"),
        label = "Home",
        isDefault = true,
    )
    private val week = MealPlanSummary(id = "p1", name = "Week 44", startDate = "2026-11-02", endDate = "2026-11-08", status = "active")
    private val other = week.copy(id = "p2", name = "Week 45")

    private val placed = mutableListOf<String>()
    private val viewed = mutableListOf<String>()
    private var managed = 0
    private var done = 0

    private fun render(addresses: List<SavedAddress> = listOf(home), tokenizer: PaymentTokenizer? = null) {
        val viewModel = CheckoutViewModel(
            useCases = CommerceUseCases(OrderRepository(remote, NoOrders()), FulfillmentRepository(remote), PaymentRepository(remote)),
            loadPlans = { listOf(week, other) },
            addressBook = Addresses(addresses),
            io = Dispatchers.Unconfined,
            tokenizer = tokenizer,
        )
        compose.setContent {
            val state by viewModel.state.collectAsState()
            val scope = rememberCoroutineScope()
            LaunchedEffect(viewModel) { viewModel.start("2026-11-02") }
            LaunchedEffect(state.placedOrderId) { state.placedOrderId?.let { placed += it } }
            NutriPlanTheme {
                CheckoutScreenContent(
                    state = state,
                    today = "2026-11-02",
                    onBack = { viewModel.back() },
                    onNext = { scope.launch { viewModel.next() } },
                    onSelectPlan = viewModel::selectPlan,
                    onSelectFulfillment = { type -> scope.launch { viewModel.selectFulfillment(type) } },
                    onSelectProvider = viewModel::selectProvider,
                    onSelectAddress = viewModel::selectAddress,
                    onManageAddresses = { managed++ },
                    onSelectDay = { day -> scope.launch { viewModel.onDateChange(day) } },
                    onSelectSlot = viewModel::selectSlot,
                    onEdit = { step -> scope.launch { viewModel.edit(step) } },
                    onRetry = {},
                    onPlaceOrder = { scope.launch { viewModel.placeOrder() } },
                    onSelectPayment = viewModel::selectPayment,
                    onSaveCardChange = viewModel::onSaveCardChange,
                    onViewOrder = { viewed += it },
                    onDone = { done++ },
                )
            }
        }
        compose.waitForIdle()
    }

    private fun next() {
        compose.onNodeWithTag(CheckoutTestTags.NEXT).performClick()
        compose.waitForIdle()
    }

    private fun choose(text: String) {
        compose.onNodeWithText(text).performScrollTo().performClick()
        compose.waitForIdle()
    }

    private fun stepTitle(@StringRes step: Int, number: Int) =
        compose.onNodeWithText(str(R.string.checkout_step_of, number, 5, str(step))).assertIsDisplayed()

    /** Plan -> pickup -> the default address -> the first slot -> review, paying with [payment]. */
    private fun walkToReview(payment: Int? = R.string.payment_type_oxxo) {
        choose("Week 44")
        next()
        choose(str(R.string.fulfillment_pickup))
        next()
        next() // the default address is already chosen
        compose.onAllNodesWithTag(CheckoutTestTags.SLOT).onFirst().performClick()
        next()
        payment?.let { choose(str(it)) }
    }

    @Test
    fun `the first step lists the plans under a heading`() {
        render()

        compose.onNode(isHeading() and hasText(str(R.string.checkout_title))).assertIsDisplayed()
        stepTitle(R.string.checkout_step_plan, 1)
        compose.onNodeWithText("Week 44").assertIsDisplayed()
        compose.onNodeWithText("Week 45").assertIsDisplayed()
    }

    @Test
    fun `moving on without a choice says what is missing`() {
        render()

        next()

        compose.onNodeWithText(str(R.string.checkout_error_plan)).assertIsDisplayed()
        stepTitle(R.string.checkout_step_plan, 1)
    }

    @Test
    fun `grocery delivery lists the stores to choose from`() {
        render()
        choose("Week 44")
        next()

        choose(str(R.string.fulfillment_grocery_delivery))

        compose.onNodeWithText(str(R.string.checkout_provider_heading)).assertIsDisplayed()
        compose.onNodeWithText("FreshBasket").assertIsDisplayed()
    }

    @Test
    fun `without saved addresses the address step offers to add one`() {
        render(addresses = emptyList())
        choose("Week 44")
        next()
        choose(str(R.string.fulfillment_pickup))
        next()

        compose.onNodeWithText(str(R.string.checkout_no_addresses_title)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.address_book_add)).performClick()

        assertEquals(1, managed)
    }

    @Test
    fun `the review shows the choices and the itemized price`() {
        render()

        walkToReview()

        stepTitle(R.string.checkout_step_review, 5)
        compose.onNodeWithText("Week 44").assertIsDisplayed()
        compose.onNodeWithText(str(R.string.fulfillment_pickup)).assertIsDisplayed()
        compose.onAllNodesWithTag(CheckoutTestTags.QUOTE_LINE).assertCountEquals(1)
        compose.onNodeWithText(str(R.string.checkout_line, "Lentil soup", "2")).assertIsDisplayed()
        compose.onNodeWithTag(CheckoutTestTags.QUOTE_TOTAL).assertIsDisplayed()
        assertEquals(listOf(OrderQuoteRequest("p1", "pickup")), remote.quotes)
    }

    @Test
    fun `a step can be edited from the review`() {
        render()
        walkToReview()

        compose.onNodeWithTag(CheckoutTestTags.edit(CheckoutStep.FULFILLMENT)).performClick()
        compose.waitForIdle()

        stepTitle(R.string.checkout_step_fulfillment, 2)
    }

    @Test
    fun `back returns to the previous step`() {
        render()
        choose("Week 44")
        next()

        compose.onNodeWithTag(CheckoutTestTags.BACK).performClick()
        compose.waitForIdle()

        stepTitle(R.string.checkout_step_plan, 1)
    }

    private fun placeOrder() {
        compose.onNodeWithTag(CheckoutTestTags.PLACE_ORDER).performClick()
        compose.waitForIdle()
    }

    @Test
    fun `placing the order sends every choice and the way to pay`() {
        render()
        walkToReview()

        placeOrder()

        val sent = remote.creates.single()
        assertEquals("p1", sent.mealPlanId)
        assertEquals("pickup", sent.fulfillmentType)
        assertEquals(home.address, sent.deliveryAddress)
        assertTrue(sent.deliveryTimeSlot.isNotBlank())
        assertEquals(PaymentMethodRequest(type = "oxxo"), sent.paymentMethod)
        assertEquals(listOf("o1"), placed)
    }

    // --- paying and the confirmation (COM-608) ---

    @Test
    fun `the review offers OXXO SPEI and PayPal but no card without the card form`() {
        render()

        walkToReview(payment = null)

        compose.onNode(isHeading() and hasText(str(R.string.checkout_pay_heading))).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.payment_type_oxxo)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.payment_type_spei)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.payment_type_paypal)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.payment_option_card)).assertDoesNotExist()
    }

    @Test
    fun `with the card form a card can be chosen and kept for next time`() {
        render(tokenizer = FakeTokenizer(TokenizationResult.Tokenized(card)))
        walkToReview(payment = R.string.payment_option_card)

        compose.onNodeWithTag(CheckoutTestTags.SAVE_CARD).performScrollTo().performClick()
        compose.waitForIdle()
        placeOrder()

        assertEquals(PaymentMethodRequest(type = "credit_card", token = "tok_visa"), remote.creates.single().paymentMethod)
        assertEquals("tok_visa", remote.saves.single().token)
    }

    @Test
    fun `the card switch only shows for a card`() {
        render(tokenizer = FakeTokenizer(TokenizationResult.Tokenized(card)))

        walkToReview()

        compose.onNodeWithTag(CheckoutTestTags.SAVE_CARD).assertDoesNotExist()
    }

    @Test
    fun `placing without a way to pay says so`() {
        render()
        walkToReview(payment = null)

        placeOrder()

        compose.onNodeWithText(str(R.string.checkout_error_payment)).assertIsDisplayed()
        assertTrue(remote.creates.isEmpty())
    }

    @Test
    fun `a card the provider cannot verify says so`() {
        render(tokenizer = FakeTokenizer(TokenizationResult.Failed))
        walkToReview(payment = R.string.payment_option_card)

        placeOrder()

        compose.onNodeWithText(str(R.string.checkout_error_card)).assertIsDisplayed()
        assertTrue(remote.creates.isEmpty())
    }

    @Test
    fun `an OXXO order shows the confirmation with the voucher and the total`() {
        remote.created = Order(
            id = "o1",
            status = "pending",
            items = listOf(OrderItem(name = "Lentil soup", quantity = 2.0, lineTotal = Money(178.0, formatted = "MXN 178.00"))),
            total = Money(178.0, formatted = "MXN 178.00"),
            voucher = PaymentVoucher(reference = "93000012345678", amount = Money(178.0, formatted = "MXN 178.00")),
        )
        render()
        walkToReview()

        placeOrder()

        compose.onNodeWithTag(CheckoutTestTags.CONFIRMATION).assertIsDisplayed()
        compose.onNode(isHeading() and hasText(str(R.string.confirmation_title))).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.confirmation_pay_now)).assertIsDisplayed()
        compose.onNodeWithTag(CheckoutTestTags.INSTRUCTIONS).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.instructions_oxxo_body, "MXN 178.00")).assertIsDisplayed()
        compose.onNodeWithText("93000012345678").assertIsDisplayed()
        compose.onNodeWithTag(CheckoutTestTags.CONFIRMATION_TOTAL).assertIsDisplayed()
        compose.onNodeWithTag(CheckoutTestTags.PLACE_ORDER).assertDoesNotExist()
    }

    @Test
    fun `a paid order is confirmed without instructions`() {
        remote.created = Order(id = "o1", status = "paid", total = Money(178.0, formatted = "MXN 178.00"))
        render(tokenizer = FakeTokenizer(TokenizationResult.Tokenized(card)))
        walkToReview(payment = R.string.payment_option_card)

        placeOrder()

        compose.onNodeWithText(str(R.string.confirmation_paid)).assertIsDisplayed()
        compose.onNodeWithTag(CheckoutTestTags.INSTRUCTIONS).assertDoesNotExist()
    }

    @Test
    fun `the confirmation opens the order or leaves the checkout`() {
        render()
        walkToReview()
        placeOrder()

        compose.onNodeWithTag(CheckoutTestTags.VIEW_ORDER).performClick()
        compose.onNodeWithTag(CheckoutTestTags.DONE).performClick()

        assertEquals(listOf("o1"), viewed)
        assertEquals(1, done)
    }

    @Test
    fun `a reorder says whose delivery it repeats`() {
        compose.setContent {
            NutriPlanTheme {
                CheckoutScreenContent(
                    state = com.nutriplan.shared.commerce.CheckoutUiState(
                        plansLoading = false,
                        plans = listOf(week),
                        reorderOf = Order(id = "o9", createdAt = "2026-10-01T10:00:00Z"),
                    ),
                    today = "2026-11-02",
                    onBack = {}, onNext = {}, onSelectPlan = {}, onSelectFulfillment = {}, onSelectProvider = {},
                    onSelectAddress = {}, onManageAddresses = {}, onSelectDay = {}, onSelectSlot = {}, onEdit = {},
                    onRetry = {}, onPlaceOrder = {},
                )
            }
        }

        val placedOn = com.nutriplan.android.screen.plans.formatPlanDay("2026-10-01")
        compose.onNodeWithText(str(R.string.checkout_reorder_note_dated, placedOn)).assertIsDisplayed()
        compose.onNodeWithTag(CheckoutTestTags.REORDER_NOTE).assertIsDisplayed()
    }

    @Test
    fun `the order cannot be placed before the price is known`() {
        compose.setContent {
            NutriPlanTheme {
                CheckoutScreenContent(
                    state = com.nutriplan.shared.commerce.CheckoutUiState(step = CheckoutStep.REVIEW, plansLoading = false, quoteLoading = true),
                    today = "2026-11-02",
                    onBack = {}, onNext = {}, onSelectPlan = {}, onSelectFulfillment = {}, onSelectProvider = {},
                    onSelectAddress = {}, onManageAddresses = {}, onSelectDay = {}, onSelectSlot = {}, onEdit = {},
                    onRetry = {}, onPlaceOrder = {},
                )
            }
        }

        compose.onNodeWithTag(CheckoutTestTags.PLACE_ORDER).assertIsNotEnabled()
    }
}
