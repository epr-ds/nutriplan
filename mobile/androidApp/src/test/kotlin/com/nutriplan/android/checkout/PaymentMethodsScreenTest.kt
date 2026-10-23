package com.nutriplan.android.checkout

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.screen.checkout.PaymentMethodsScreenContent
import com.nutriplan.android.screen.checkout.PaymentMethodsTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.commerce.NewPaymentMethod
import com.nutriplan.shared.commerce.OrderError
import com.nutriplan.shared.commerce.PaymentMethodsUiState
import com.nutriplan.shared.commerce.PaymentMethodsViewModel
import com.nutriplan.shared.commerce.PaymentTokenizer
import com.nutriplan.shared.commerce.TokenizationResult
import com.nutriplan.shared.data.model.CancelOrderRequest
import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.GrocerySearchRequest
import com.nutriplan.shared.data.model.KitchenAvailability
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderListQuery
import com.nutriplan.shared.data.model.PaymentMethod
import com.nutriplan.shared.data.model.SavePaymentMethodRequest
import com.nutriplan.shared.data.repository.CommerceRepository
import com.nutriplan.shared.data.repository.PaymentRepository
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * COM-603: the payment-method screen lists saved methods, adds one through the provider's tokenizer
 * and deletes after confirmation, with loading, empty and error states. Runs on the JVM via
 * Robolectric.
 */
@RunWith(AndroidJUnit4::class)
// A tall viewport so every lazily composed item is on screen.
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2400dp", application = TestApplication::class)
class PaymentMethodsScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    /** A Commerce client holding the saved methods server-side. */
    private class FakeCommerce : CommerceRepository {
        val methods = mutableListOf<PaymentMethod>()

        override suspend fun listPaymentMethods(): List<PaymentMethod> = methods.toList()

        override suspend fun savePaymentMethod(request: SavePaymentMethodRequest): PaymentMethod =
            PaymentMethod(id = "pm-new", type = request.type, brand = request.brand, last4 = request.last4).also { methods.add(0, it) }

        override suspend fun deletePaymentMethod(paymentMethodId: String) {
            methods.removeAll { it.id == paymentMethodId }
        }

        override suspend fun createOrder(request: CreateOrderRequest, idempotencyKey: String?): Order = error("unused")
        override suspend fun listOrders(query: OrderListQuery): List<Order> = error("unused")
        override suspend fun getOrder(orderId: String): Order = error("unused")
        override suspend fun cancelOrder(orderId: String, request: CancelOrderRequest?): Order = error("unused")
        override suspend fun syncGroceryOrder(orderId: String): Order = error("unused")
        override suspend fun darkKitchenAvailability(zipCode: String, deliveryDate: String?): KitchenAvailability = error("unused")
        override suspend fun searchGroceryProducts(request: GrocerySearchRequest): List<FulfillmentProvider> = error("unused")
        override suspend fun groceryProviders(): List<FulfillmentProvider> = error("unused")
    }

    private val remote = FakeCommerce()
    private val visa = PaymentMethod(id = "pm-visa", type = "credit_card", brand = "visa", last4 = "4242", expMonth = 3, expYear = 2030)
    private val paypal = PaymentMethod(id = "pm-pp", type = "paypal")

    private val tokenizer = object : PaymentTokenizer {
        override suspend fun tokenize(): TokenizationResult =
            TokenizationResult.Tokenized(NewPaymentMethod("credit_card", "tok_mc", brand = "mastercard", last4 = "4444"))
    }

    private val visaName get() = str(R.string.payment_methods_card_name, "Visa", "4242")

    /** Render the screen bound to a real view model, wired the way [PaymentMethodsScreen] wires it. */
    private fun renderWithViewModel(withTokenizer: Boolean = true) {
        val viewModel = PaymentMethodsViewModel(PaymentRepository(remote), tokenizer.takeIf { withTokenizer })
        runBlocking { viewModel.load() }
        compose.setContent {
            val state by viewModel.state.collectAsState()
            val scope = rememberCoroutineScope()
            NutriPlanTheme {
                PaymentMethodsScreenContent(
                    state = state,
                    onBack = {},
                    onRetry = { scope.launch { viewModel.load() } },
                    onAdd = { scope.launch { viewModel.add() } },
                    onRequestDelete = viewModel::requestDelete,
                    onConfirmDelete = { scope.launch { viewModel.confirmDelete() } },
                    onCancelDelete = viewModel::cancelDelete,
                    onDismissError = viewModel::dismissError,
                )
            }
        }
    }

    private fun renderState(state: PaymentMethodsUiState, onRetry: () -> Unit = {}, onDismissError: () -> Unit = {}) {
        compose.setContent {
            NutriPlanTheme {
                PaymentMethodsScreenContent(
                    state = state,
                    onBack = {},
                    onRetry = onRetry,
                    onAdd = {},
                    onRequestDelete = {},
                    onConfirmDelete = {},
                    onCancelDelete = {},
                    onDismissError = onDismissError,
                )
            }
        }
    }

    // --- states ---

    @Test
    fun `while loading a labelled progress indicator is shown`() {
        renderState(PaymentMethodsUiState(isLoading = true))

        compose.onNodeWithTag(PaymentMethodsTestTags.LOADING).assertIsDisplayed()
        compose.onNodeWithContentDescription(str(R.string.cd_payment_methods_loading)).assertExists()
    }

    @Test
    fun `the title is a heading`() {
        renderWithViewModel()

        compose.onNode(isHeading() and hasText(str(R.string.payment_methods_title))).assertIsDisplayed()
    }

    @Test
    fun `without the provider form there is nothing to add`() {
        renderWithViewModel(withTokenizer = false)

        compose.onNodeWithTag(PaymentMethodsTestTags.EMPTY).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.payment_methods_empty_description)).assertIsDisplayed()
        compose.onNodeWithTag(PaymentMethodsTestTags.ADD).assertDoesNotExist()
    }

    @Test
    fun `with the provider form an empty list offers to add and explains the card stays with the provider`() {
        renderWithViewModel()

        compose.onNodeWithText(str(R.string.payment_methods_empty_add_description)).assertIsDisplayed()
        compose.onNodeWithTag(PaymentMethodsTestTags.ADD).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.payment_methods_secure_note)).assertIsDisplayed()
    }

    @Test
    fun `a list that cannot be loaded offers to retry`() {
        var retries = 0
        renderState(PaymentMethodsUiState(isLoading = false, loadError = OrderError.NETWORK), onRetry = { retries++ })

        compose.onNodeWithText(str(R.string.error_payment_methods_network)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.payment_methods_retry)).performClick()

        assertEquals(1, retries)
    }

    @Test
    fun `a failed action is announced and can be dismissed`() {
        var dismissed = 0
        renderState(
            PaymentMethodsUiState(isLoading = false, methods = listOf(visa), actionError = OrderError.SERVER_PROBLEM),
            onDismissError = { dismissed++ },
        )

        compose.onNodeWithTag(PaymentMethodsTestTags.ERROR_BANNER).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.error_payment_methods_server)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.payment_methods_dismiss)).performClick()

        assertEquals(1, dismissed)
    }

    // --- list ---

    @Test
    fun `saved methods are listed by brand last four and expiry`() {
        remote.methods += listOf(visa, paypal)
        renderWithViewModel()

        compose.onAllNodesWithTag(PaymentMethodsTestTags.METHOD_CARD).assertCountEquals(2)
        compose.onNodeWithText(visaName).assertIsDisplayed()
        compose.onNodeWithText(
            "${str(R.string.payment_type_credit_card)} · ${str(R.string.payment_methods_expires, "03", "2030")}",
        ).assertIsDisplayed()
        // The name and the type line, inside the merged card.
        compose.onAllNodesWithText(str(R.string.payment_type_paypal), useUnmergedTree = true).assertCountEquals(2)
    }

    // --- add and delete ---

    @Test
    fun `a method is added through the provider form`() {
        renderWithViewModel()

        compose.onNodeWithTag(PaymentMethodsTestTags.ADD).performClick()
        compose.waitForIdle()

        assertEquals(listOf("4444"), remote.methods.map { it.last4 })
        compose.onNodeWithText(str(R.string.payment_methods_card_name, "Mastercard", "4444")).assertIsDisplayed()
    }

    @Test
    fun `a method is deleted after confirming`() {
        remote.methods += visa
        renderWithViewModel()

        compose.onNodeWithContentDescription(str(R.string.cd_payment_methods_delete, visaName)).performClick()
        compose.onNodeWithText(str(R.string.payment_methods_delete_title)).assertIsDisplayed()
        compose.onNodeWithTag(PaymentMethodsTestTags.CONFIRM_DELETE).performClick()
        compose.waitForIdle()

        assertTrue(remote.methods.isEmpty())
        compose.onNodeWithTag(PaymentMethodsTestTags.METHOD_CARD).assertDoesNotExist()
    }

    @Test
    fun `keeping a method closes the dialog and deletes nothing`() {
        remote.methods += visa
        renderWithViewModel()

        compose.onNodeWithContentDescription(str(R.string.cd_payment_methods_delete, visaName)).performClick()
        compose.onNodeWithText(str(R.string.payment_methods_keep)).performClick()

        compose.onNodeWithText(str(R.string.payment_methods_delete_title)).assertDoesNotExist()
        assertEquals(listOf(visa), remote.methods)
    }
}
