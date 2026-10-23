package com.nutriplan.shared.commerce

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
import com.nutriplan.shared.data.repository.PaymentRepository
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** COM-603: the payment-method screen lists, adds (through the provider's tokenizer) and deletes. */
class PaymentMethodsViewModelTest {

    /** A Commerce client holding the saved methods server-side; [failNext] makes the next call throw it. */
    private class FakeCommerce : CommerceRepository {
        val methods = mutableListOf<PaymentMethod>()
        val saves = mutableListOf<SavePaymentMethodRequest>()
        var failNext: Throwable? = null

        private fun maybeFail() {
            failNext?.let {
                failNext = null
                throw it
            }
        }

        override suspend fun listPaymentMethods(): List<PaymentMethod> {
            maybeFail()
            return methods.toList()
        }

        override suspend fun savePaymentMethod(request: SavePaymentMethodRequest): PaymentMethod {
            maybeFail()
            saves += request
            return PaymentMethod(id = "pm${methods.size + 1}", type = request.type, brand = request.brand, last4 = request.last4)
                .also { methods.add(0, it) }
        }

        override suspend fun deletePaymentMethod(paymentMethodId: String) {
            maybeFail()
            if (!methods.removeAll { it.id == paymentMethodId }) throw ApiException.HttpError(statusCode = 404, body = "{}")
        }

        override suspend fun createOrder(request: CreateOrderRequest, idempotencyKey: String?): Order = error("unused")

        override suspend fun quoteOrder(request: OrderQuoteRequest): OrderQuote = error("unused")

        override suspend fun listOrders(query: OrderListQuery): List<Order> = error("unused")

        override suspend fun getOrder(orderId: String): Order = error("unused")

        override suspend fun cancelOrder(orderId: String, request: CancelOrderRequest?): Order = error("unused")

        override suspend fun syncGroceryOrder(orderId: String): Order = error("unused")

        override suspend fun darkKitchenAvailability(zipCode: String, deliveryDate: String?): KitchenAvailability =
            error("unused")

        override suspend fun searchGroceryProducts(request: GrocerySearchRequest): List<FulfillmentProvider> =
            error("unused")

        override suspend fun groceryProviders(): List<FulfillmentProvider> = error("unused")
    }

    private val remote = FakeCommerce()
    private val visa = PaymentMethod(id = "pm-visa", type = "credit_card", brand = "visa", last4 = "4242", expMonth = 12, expYear = 2030)
    private val offline = ApiException.NetworkError(errorCause = Exception("no route to host"))

    private var nextTokenization: TokenizationResult =
        TokenizationResult.Tokenized(NewPaymentMethod("credit_card", "tok_mc", brand = "mastercard", last4 = "4444"))
    private val tokenizer = object : PaymentTokenizer {
        override suspend fun tokenize(): TokenizationResult = nextTokenization
    }

    private fun viewModel(withTokenizer: Boolean = true) =
        PaymentMethodsViewModel(PaymentRepository(remote), tokenizer.takeIf { withTokenizer })

    // --- list ---

    @Test
    fun `it starts loading and then shows the saved methods`() = runTest {
        remote.methods += visa
        val viewModel = viewModel()
        assertTrue(viewModel.state.value.isLoading)

        viewModel.load()

        assertEquals(listOf(visa), viewModel.state.value.methods)
        assertFalse(viewModel.state.value.isEmpty)
    }

    @Test
    fun `with nothing saved the screen is empty`() = runTest {
        val viewModel = viewModel()

        viewModel.load()

        assertTrue(viewModel.state.value.isEmpty)
    }

    @Test
    fun `a list that cannot be loaded says why`() = runTest {
        remote.failNext = offline
        val viewModel = viewModel()

        viewModel.load()

        assertEquals(OrderError.NETWORK, viewModel.state.value.loadError)
        assertFalse(viewModel.state.value.isEmpty, "an error is not an empty list")
    }

    @Test
    fun `a rejected session asks the user to sign in again`() = runTest {
        remote.failNext = ApiException.HttpError(statusCode = 401, body = "{}")
        val viewModel = viewModel()

        viewModel.load()

        assertTrue(viewModel.state.value.sessionExpired)
    }

    // --- add ---

    @Test
    fun `methods can be added only when a provider tokenizer is available`() = runTest {
        assertTrue(viewModel(withTokenizer = true).state.value.canAdd)

        val without = viewModel(withTokenizer = false)
        assertFalse(without.state.value.canAdd)
        assertFalse(without.add())
        assertTrue(remote.saves.isEmpty())
    }

    @Test
    fun `adding saves the provider token and refreshes the list`() = runTest {
        val viewModel = viewModel()
        viewModel.load()

        assertTrue(viewModel.add())

        assertEquals("tok_mc", remote.saves.single().token)
        assertEquals(listOf("4444"), viewModel.state.value.methods.map { it.last4 })
        assertFalse(viewModel.state.value.isAdding)
    }

    @Test
    fun `closing the provider form adds nothing and shows no error`() = runTest {
        nextTokenization = TokenizationResult.Cancelled
        val viewModel = viewModel()
        viewModel.load()

        assertFalse(viewModel.add())

        assertTrue(remote.saves.isEmpty())
        assertNull(viewModel.state.value.addError)
        assertNull(viewModel.state.value.actionError)
    }

    @Test
    fun `a card the provider cannot tokenize is reported`() = runTest {
        nextTokenization = TokenizationResult.Failed
        val viewModel = viewModel()
        viewModel.load()

        assertFalse(viewModel.add())

        assertEquals(AddPaymentMethodError.TOKENIZATION_FAILED, viewModel.state.value.addError)
        assertTrue(remote.saves.isEmpty())
    }

    @Test
    fun `a card number from a broken tokenizer is never sent`() = runTest {
        nextTokenization = TokenizationResult.Tokenized(NewPaymentMethod("credit_card", "4242424242424242"))
        val viewModel = viewModel()
        viewModel.load()

        assertFalse(viewModel.add())

        assertEquals(OrderError.REJECTED, viewModel.state.value.actionError)
        assertTrue(remote.saves.isEmpty())
    }

    @Test
    fun `a save that fails is reported and the list stays`() = runTest {
        remote.methods += visa
        val viewModel = viewModel()
        viewModel.load()
        remote.failNext = offline

        assertFalse(viewModel.add())

        assertEquals(OrderError.NETWORK, viewModel.state.value.actionError)
        assertEquals(listOf(visa), viewModel.state.value.methods)
    }

    @Test
    fun `errors can be dismissed`() = runTest {
        nextTokenization = TokenizationResult.Failed
        val viewModel = viewModel()
        viewModel.add()

        viewModel.dismissError()

        assertNull(viewModel.state.value.addError)
    }

    // --- delete ---

    @Test
    fun `deleting asks for confirmation first`() = runTest {
        remote.methods += visa
        val viewModel = viewModel()
        viewModel.load()

        viewModel.requestDelete(visa)
        assertEquals(visa, viewModel.state.value.confirmingDelete)
        viewModel.cancelDelete()

        assertNull(viewModel.state.value.confirmingDelete)
        assertEquals(listOf(visa), remote.methods)
    }

    @Test
    fun `a confirmed delete removes the method`() = runTest {
        remote.methods += visa
        val viewModel = viewModel()
        viewModel.load()

        viewModel.requestDelete(visa)
        viewModel.confirmDelete()

        assertTrue(remote.methods.isEmpty())
        assertTrue(viewModel.state.value.isEmpty)
        assertNull(viewModel.state.value.confirmingDelete)
    }

    @Test
    fun `a method that is already gone counts as deleted`() = runTest {
        val viewModel = viewModel()
        viewModel.requestDelete(visa)

        viewModel.confirmDelete()

        assertNull(viewModel.state.value.actionError)
    }

    @Test
    fun `a delete that fails is reported and the method stays`() = runTest {
        remote.methods += visa
        val viewModel = viewModel()
        viewModel.load()
        viewModel.requestDelete(visa)
        remote.failNext = ApiException.HttpError(statusCode = 503, body = "{}")

        viewModel.confirmDelete()

        assertEquals(OrderError.SERVER_PROBLEM, viewModel.state.value.actionError)
        assertEquals(listOf(visa), viewModel.state.value.methods)
    }
}
