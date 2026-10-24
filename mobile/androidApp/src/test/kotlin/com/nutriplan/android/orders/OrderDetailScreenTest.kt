package com.nutriplan.android.orders

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.screen.checkout.CheckoutTestTags
import com.nutriplan.android.screen.orders.OrderDetailScreenContent
import com.nutriplan.android.screen.orders.OrderDetailTestTags
import com.nutriplan.android.screen.orders.formatOrderTime
import com.nutriplan.android.screen.plans.formatPlanDay
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.commerce.OrderDetailUiState
import com.nutriplan.shared.commerce.OrderError
import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.Money
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderAddress
import com.nutriplan.shared.data.model.OrderItem
import com.nutriplan.shared.data.model.OrderStatusChange
import com.nutriplan.shared.data.model.PaymentVoucher
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * COM-703: the order detail shows the status timeline, the items and totals, and the delivery;
 * offers cancel (after confirming) only before dispatch; shows what is left to pay for a pending
 * OXXO order; and has loading, error and offline states. Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2400dp", application = TestApplication::class)
class OrderDetailScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private val order = Order(
        id = "o1",
        status = "preparing",
        fulfillmentType = "grocery_delivery",
        provider = FulfillmentProvider(id = "freshbasket", name = "FreshBasket"),
        deliveryAddress = OrderAddress(
            street = "Reforma 222",
            apartment = "4B",
            city = "CDMX",
            state = "CDMX",
            zipCode = "06600",
            country = "MX",
            instructions = "Ring twice",
        ),
        deliveryDate = "2026-11-02",
        deliveryTimeSlot = "13:00-15:00",
        createdAt = "2026-10-23T18:00:00Z",
        statusHistory = listOf(
            OrderStatusChange("pending", "confirmed", "2026-10-23T18:05:00Z"),
            OrderStatusChange("confirmed", "preparing", "2026-10-23T19:00:00Z"),
        ),
        items = listOf(
            OrderItem(name = "Lentil soup", quantity = 2.0, lineTotal = Money(178.0, formatted = "MXN 178.00")),
            OrderItem(name = "Salmon", quantity = 1.0, lineTotal = Money(85.0, formatted = "MXN 85.00")),
        ),
        subtotal = Money(263.0, formatted = "MXN 263.00"),
        deliveryFee = Money(49.0, formatted = "MXN 49.00"),
        total = Money(312.0, formatted = "MXN 312.00"),
    )

    private var retries = 0
    private var cancelRequests = 0
    private var confirmed = 0
    private var kept = 0

    private fun render(state: OrderDetailUiState) {
        compose.setContent {
            NutriPlanTheme {
                OrderDetailScreenContent(
                    state = state,
                    onBack = {},
                    onRetry = { retries++ },
                    onRequestCancel = { cancelRequests++ },
                    onConfirmCancel = { confirmed++ },
                    onDismissCancel = { kept++ },
                    onDismissCancelError = {},
                )
            }
        }
        compose.waitForIdle()
    }

    private fun loaded(order: Order = this.order) = OrderDetailUiState(isLoading = false, order = order)

    @Test
    fun `the title and sections are headings`() {
        render(loaded())

        compose.onNode(isHeading() and hasText(str(R.string.order_detail_title))).assertIsDisplayed()
        compose.onNode(isHeading() and hasText(str(R.string.order_detail_status_heading))).assertIsDisplayed()
        compose.onNode(isHeading() and hasText(str(R.string.order_detail_items_heading))).assertIsDisplayed()
        compose.onNode(isHeading() and hasText(str(R.string.order_detail_delivery_heading))).assertIsDisplayed()
    }

    @Test
    fun `the timeline shows each step with when it was reached`() {
        render(loaded())

        compose.onAllNodesWithTag(OrderDetailTestTags.TIMELINE_STEP).assertCountEquals(5)
        val preparing = str(R.string.order_timeline_step, str(R.string.order_status_preparing), str(R.string.order_timeline_current))
        val reached = formatOrderTime("2026-10-23T19:00:00Z")
        compose.onNode(hasContentDescription("$preparing, $reached")).assertIsDisplayed()
        val delivered = str(R.string.order_timeline_step, str(R.string.order_status_delivered), str(R.string.order_timeline_upcoming))
        compose.onNode(hasContentDescription(delivered)).assertIsDisplayed()
    }

    @Test
    fun `the items and totals are listed`() {
        render(loaded())

        compose.onAllNodesWithTag(OrderDetailTestTags.ITEM).assertCountEquals(2)
        compose.onNodeWithText(str(R.string.checkout_line, "Lentil soup", "2")).assertIsDisplayed()
        compose.onNodeWithText("MXN 49.00").assertIsDisplayed()
        compose.onNodeWithTag(OrderDetailTestTags.TOTAL).assertIsDisplayed()
        compose.onNodeWithText("MXN 312.00").assertIsDisplayed()
    }

    @Test
    fun `the delivery shows how when and where`() {
        render(loaded())

        val how = "${str(R.string.fulfillment_grocery_delivery)} · ${str(R.string.order_detail_store, "FreshBasket")}"
        compose.onNodeWithText(how).assertIsDisplayed()
        compose.onNodeWithText("${formatPlanDay("2026-11-02")}, 13:00-15:00").assertIsDisplayed()
        compose.onNodeWithText("Reforma 222, 4B").assertIsDisplayed()
        compose.onNodeWithText("CDMX, CDMX 06600").assertIsDisplayed()
        compose.onNodeWithText(str(R.string.order_detail_instructions, "Ring twice")).assertIsDisplayed()
    }

    @Test
    fun `cancel is offered before dispatch and asks first`() {
        render(loaded())

        compose.onNodeWithTag(OrderDetailTestTags.CANCEL).performClick()

        assertEquals(1, cancelRequests)
    }

    @Test
    fun `the confirmation cancels or keeps the order`() {
        render(loaded().copy(confirmingCancel = true))

        compose.onNodeWithText(str(R.string.order_detail_cancel_title)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.order_detail_keep)).performClick()
        compose.onNodeWithTag(OrderDetailTestTags.CONFIRM_CANCEL).performClick()

        assertEquals(1, kept)
        assertEquals(1, confirmed)
    }

    @Test
    fun `a dispatched order offers no cancel`() {
        render(loaded(order.copy(status = "in_transit")))

        compose.onAllNodesWithTag(OrderDetailTestTags.CANCEL).assertCountEquals(0)
    }

    @Test
    fun `a cancellation that failed says why`() {
        render(loaded(order.copy(status = "in_transit")).copy(cancelError = OrderError.CONFLICT))

        compose.onNodeWithTag(OrderDetailTestTags.CANCEL_ERROR).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.error_order_cancel_conflict)).assertIsDisplayed()
    }

    @Test
    fun `a pending OXXO order shows the voucher`() {
        val voucher = PaymentVoucher(reference = "9300 1234", amount = Money(312.0, formatted = "MXN 312.00"))
        render(loaded(order.copy(status = "pending", statusHistory = emptyList(), voucher = voucher)))

        compose.onNodeWithTag(CheckoutTestTags.INSTRUCTIONS).assertIsDisplayed()
        compose.onNodeWithText("9300 1234").assertIsDisplayed()
    }

    @Test
    fun `loading shows progress`() {
        render(OrderDetailUiState())

        compose.onNodeWithTag(OrderDetailTestTags.LOADING).assertIsDisplayed()
    }

    @Test
    fun `an order that cannot be loaded says why and can be retried`() {
        render(OrderDetailUiState(isLoading = false, loadError = OrderError.NOT_FOUND))

        compose.onNodeWithText(str(R.string.error_order_not_found)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.orders_retry)).performClick()

        assertEquals(1, retries)
    }

    @Test
    fun `the saved copy shown offline carries a note`() {
        render(loaded().copy(refreshError = OrderError.NETWORK))

        compose.onNodeWithTag(OrderDetailTestTags.STALE).assertIsDisplayed()
    }
}
