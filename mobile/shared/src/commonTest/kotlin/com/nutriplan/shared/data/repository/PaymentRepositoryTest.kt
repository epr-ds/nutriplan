package com.nutriplan.shared.data.repository

import com.nutriplan.shared.commerce.NewPaymentMethod
import com.nutriplan.shared.commerce.OrderError
import com.nutriplan.shared.commerce.OrderResult
import com.nutriplan.shared.data.model.CancelOrderRequest
import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.GrocerySearchRequest
import com.nutriplan.shared.data.model.KitchenAvailability
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderListQuery
import com.nutriplan.shared.data.model.PaymentMethod
import com.nutriplan.shared.data.model.SavePaymentMethodRequest
import com.nutriplan.shared.data.network.ApiException
import kotlinx.coroutines.test.runTest
import kotlin.coroutines.cancellation.CancellationException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * COM-506: saved payment methods go through a clean repository -- tokens only, nothing kept on the
 * device, a card number refused before it is ever sent, and typed results.
 */
class PaymentRepositoryTest {

    /** A Commerce client whose payment-method answers each test sets; a [Throwable] answer is thrown. */
    private class FakeCommerce : CommerceRepository {
        var list: Any = listOf(card)
        var saved: Any = card
        var deleted: Any = Unit
        val saves = mutableListOf<SavePaymentMethodRequest>()
        val deletes = mutableListOf<String>()

        @Suppress("UNCHECKED_CAST")
        private fun <T> answer(value: Any): T = if (value is Throwable) throw value else value as T

        override suspend fun listPaymentMethods(): List<PaymentMethod> = answer(list)

        override suspend fun savePaymentMethod(request: SavePaymentMethodRequest): PaymentMethod {
            saves += request
            return answer(saved)
        }

        override suspend fun deletePaymentMethod(paymentMethodId: String) {
            deletes += paymentMethodId
            answer<Unit>(deleted)
        }

        override suspend fun createOrder(request: CreateOrderRequest, idempotencyKey: String?): Order = error("unused")

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
    private val payments = PaymentRepository(remote)

    private val offline = ApiException.NetworkError(errorCause = Exception("no route to host"))
    private fun http(status: Int) = ApiException.HttpError(statusCode = status, body = """{"status":$status}""")

    private val visa = NewPaymentMethod("credit_card", "tok_visa_123", brand = "visa", last4 = "4242", expMonth = 12, expYear = 2030)

    // --- list ---

    @Test
    fun `the saved methods are listed with their display details only`() = runTest {
        val result = payments.paymentMethods()

        assertEquals(OrderResult.Success(listOf(card)), result)
    }

    @Test
    fun `no saved methods is an empty success`() = runTest {
        remote.list = emptyList<PaymentMethod>()

        assertEquals(OrderResult.Success(emptyList()), payments.paymentMethods())
    }

    @Test
    fun `the list is always the server's because nothing is kept on the device`() = runTest {
        payments.paymentMethods()
        remote.list = listOf(wallet)

        assertEquals(OrderResult.Success(listOf(wallet)), payments.paymentMethods())
    }

    @Test
    fun `listing offline is a network failure`() = runTest {
        remote.list = offline

        assertEquals(OrderResult.Failure(OrderError.NETWORK), payments.paymentMethods())
    }

    // --- add ---

    @Test
    fun `a card is saved from its token and display details`() = runTest {
        val result = payments.addPaymentMethod(visa)

        assertEquals(OrderResult.Success(card), result)
        assertEquals(
            SavePaymentMethodRequest("credit_card", "tok_visa_123", brand = "visa", last4 = "4242", expMonth = 12, expYear = 2030),
            remote.saves.single(),
        )
    }

    @Test
    fun `a wallet is saved from its token alone`() = runTest {
        remote.saved = wallet

        payments.addPaymentMethod(NewPaymentMethod("paypal", "  tok_pp  ", brand = " "))

        assertEquals(SavePaymentMethodRequest("paypal", "tok_pp"), remote.saves.single())
    }

    @Test
    fun `a card number in place of a token is refused without a call`() = runTest {
        listOf("4242424242424242", "4242 4242 4242 4242", "5555-5555-5555-4444", "378282246310005").forEach { number ->
            val result = payments.addPaymentMethod(NewPaymentMethod("credit_card", number, last4 = number.takeLast(4)))
            assertEquals(OrderResult.Failure(OrderError.REJECTED), result, number)
        }
        assertTrue(remote.saves.isEmpty(), "no card number was sent")
    }

    @Test
    fun `malformed details are refused without a call`() = runTest {
        val bad = listOf(
            NewPaymentMethod("credit_card", " "),
            NewPaymentMethod("card", "tok_1"),
            NewPaymentMethod("credit_card", "tok_1", last4 = "42"),
            NewPaymentMethod("credit_card", "tok_1", last4 = "42a4"),
            NewPaymentMethod("credit_card", "tok_1", expMonth = 13),
            NewPaymentMethod("credit_card", "tok_1", expMonth = 0),
            NewPaymentMethod("credit_card", "tok_1", expYear = 1999),
        )

        bad.forEach { method ->
            assertEquals(OrderResult.Failure(OrderError.REJECTED), payments.addPaymentMethod(method), method.toString())
        }
        assertTrue(remote.saves.isEmpty())
    }

    @Test
    fun `numeric tokens that are not card numbers are allowed`() = runTest {
        // Too short to be a card number, and 16 digits that fail the Luhn check.
        payments.addPaymentMethod(NewPaymentMethod("oxxo", "1234567890"))
        payments.addPaymentMethod(NewPaymentMethod("spei", "4242424242424241"))

        assertEquals(listOf("1234567890", "4242424242424241"), remote.saves.map { it.token })
    }

    @Test
    fun `save failures are typed`() = runTest {
        val expected = mapOf(
            offline to OrderError.NETWORK,
            http(401) to OrderError.SESSION_EXPIRED,
            http(422) to OrderError.REJECTED,
            http(503) to OrderError.SERVER_PROBLEM,
        )

        expected.forEach { (failure, error) ->
            remote.saved = failure
            assertEquals(OrderResult.Failure(error), payments.addPaymentMethod(visa), error.name)
        }
    }

    // --- delete ---

    @Test
    fun `a saved method is deleted`() = runTest {
        assertEquals(OrderResult.Success(Unit), payments.deletePaymentMethod("pm1"))
        assertEquals(listOf("pm1"), remote.deletes)
    }

    @Test
    fun `deleting a method that is already gone is not found`() = runTest {
        remote.deleted = http(404)

        assertEquals(OrderResult.Failure(OrderError.NOT_FOUND), payments.deletePaymentMethod("pm1"))
    }

    @Test
    fun `deleting without an id is refused without a call`() = runTest {
        assertEquals(OrderResult.Failure(OrderError.REJECTED), payments.deletePaymentMethod(" "))
        assertTrue(remote.deletes.isEmpty())
    }

    // --- safe to log ---

    @Test
    fun `a new payment method never prints its token`() {
        val text = visa.toString()

        assertFalse("tok_visa_123" in text, text)
        assertTrue("<redacted>" in text)
        assertTrue("last4=4242" in text)
    }

    @Test
    fun `card numbers are recognised by their length and checksum`() {
        assertTrue("4242424242424242".looksLikeCardNumber())
        assertTrue("4111 1111 1111 1111".looksLikeCardNumber())
        assertTrue("3782-822463-10005".looksLikeCardNumber())
        assertFalse("4242424242424241".looksLikeCardNumber(), "fails the Luhn check")
        assertFalse("42424242".looksLikeCardNumber(), "too short")
        assertFalse("tok_4242424242424242".looksLikeCardNumber(), "not only digits")
    }

    @Test
    fun `cancellation of the caller is never swallowed`() = runTest {
        remote.list = CancellationException("left the screen")

        assertFailsWith<CancellationException> { payments.paymentMethods() }
    }

    private companion object {
        val card = PaymentMethod(id = "pm1", type = "credit_card", brand = "visa", last4 = "4242", expMonth = 12, expYear = 2030)
        val wallet = PaymentMethod(id = "pm2", type = "paypal")
    }
}
