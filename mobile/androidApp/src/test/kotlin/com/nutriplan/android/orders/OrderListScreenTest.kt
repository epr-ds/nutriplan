package com.nutriplan.android.orders

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.screen.orders.OrderListScreenContent
import com.nutriplan.android.screen.orders.OrderListTestTags
import com.nutriplan.android.screen.plans.formatPlanDay
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.commerce.OrderError
import com.nutriplan.shared.commerce.OrderFilter
import com.nutriplan.shared.commerce.OrderListUiState
import com.nutriplan.shared.data.model.Money
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderItem
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * COM-701: the order list shows each order's status, delivery, items and total; filters by status
 * with counts; offers reorder; and has loading, empty and error states. Runs on the JVM via
 * Robolectric.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2400dp", application = TestApplication::class)
class OrderListScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private val pending = Order(
        id = "o1",
        status = "pending",
        fulfillmentType = "dark_kitchen",
        deliveryDate = "2026-11-02",
        deliveryTimeSlot = "13:00-15:00",
        createdAt = "2026-10-23T18:00:00Z",
        items = listOf(OrderItem(name = "Lentil soup"), OrderItem(name = "Salmon"), OrderItem(name = "Oatmeal")),
        total = Money(208.0, formatted = "MXN 208.00"),
    )
    private val delivered = Order(
        id = "o2",
        status = "delivered",
        fulfillmentType = "pickup",
        createdAt = "2026-10-01T10:00:00Z",
        items = listOf(OrderItem(name = "Chicken bowl")),
        total = Money(150.0, formatted = "MXN 150.00"),
    )
    private val unknownKind = Order(id = "o3", status = "cancelled", total = Money(90.0, formatted = "MXN 90.00"))

    private val opened = mutableListOf<String>()
    private val reordered = mutableListOf<String>()
    private var retries = 0
    private var browsed = 0

    private fun render(initial: OrderListUiState) {
        compose.setContent {
            var state by remember { mutableStateOf(initial) }
            NutriPlanTheme {
                OrderListScreenContent(
                    state = state,
                    canReorder = { it.fulfillmentType != null },
                    onBack = {},
                    onRetry = { retries++ },
                    onSelectFilter = { filter -> state = state.copy(filter = filter) },
                    onOrderClick = { opened += it },
                    onReorder = { reordered += it },
                    onBrowsePlans = { browsed++ },
                )
            }
        }
        compose.waitForIdle()
    }

    private fun loaded(vararg orders: Order) = OrderListUiState(isLoading = false, orders = orders.toList())

    @Test
    fun `the title is a heading`() {
        render(loaded(pending))

        compose.onNode(isHeading() and hasText(str(R.string.orders_title))).assertIsDisplayed()
    }

    @Test
    fun `each order shows its status delivery items and total`() {
        render(loaded(pending, delivered))

        compose.onAllNodesWithTag(OrderListTestTags.ORDER_CARD).assertCountEquals(2)
        compose.onNodeWithText(str(R.string.orders_placed_on, formatPlanDay("2026-10-23"))).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.order_status_pending)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.order_status_delivered)).assertIsDisplayed()
        val delivery = str(R.string.orders_delivery_on, formatPlanDay("2026-11-02"), "13:00-15:00")
        compose.onNodeWithText("${str(R.string.fulfillment_dark_kitchen)} · $delivery").assertIsDisplayed()
        compose.onNodeWithText(str(R.string.orders_items_more, "Lentil soup", 2)).assertIsDisplayed()
        compose.onNodeWithText("Chicken bowl").assertIsDisplayed()
        compose.onNodeWithText("MXN 208.00").assertIsDisplayed()
    }

    @Test
    fun `the filters show their counts and filter the list`() {
        render(loaded(pending, delivered, unknownKind))

        compose.onNodeWithText(str(R.string.orders_filter_count, str(R.string.orders_filter_all), 3)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.orders_filter_count, str(R.string.orders_filter_active), 1)).assertIsDisplayed()
        compose.onNodeWithTag(OrderListTestTags.filter(OrderFilter.DELIVERED)).performClick()
        compose.waitForIdle()

        compose.onNodeWithTag(OrderListTestTags.filter(OrderFilter.DELIVERED)).assertIsSelected()
        compose.onAllNodesWithTag(OrderListTestTags.ORDER_CARD).assertCountEquals(1)
        compose.onNodeWithText("MXN 150.00").assertIsDisplayed()
    }

    @Test
    fun `a filter with no orders says so`() {
        render(loaded(pending).copy(filter = OrderFilter.CANCELLED))

        compose.onNodeWithTag(OrderListTestTags.FILTERED_EMPTY).assertIsDisplayed()
        compose.onAllNodesWithTag(OrderListTestTags.ORDER_CARD).assertCountEquals(0)
    }

    @Test
    fun `an order opens and can be reordered`() {
        render(loaded(pending))

        compose.onNodeWithTag(OrderListTestTags.REORDER).performClick()
        compose.onAllNodesWithTag(OrderListTestTags.ORDER_CARD).onFirst().performClick()

        assertEquals(listOf("o1"), reordered)
        assertEquals(listOf("o1"), opened)
    }

    @Test
    fun `an order the checkout cannot repeat offers no reorder`() {
        render(loaded(unknownKind))

        compose.onAllNodesWithTag(OrderListTestTags.REORDER).assertCountEquals(0)
        compose.onNodeWithText(str(R.string.orders_order)).assertIsDisplayed()
    }

    @Test
    fun `loading shows progress`() {
        render(OrderListUiState())

        compose.onNodeWithTag(OrderListTestTags.LOADING).assertIsDisplayed()
    }

    @Test
    fun `no orders offers the meal plans`() {
        render(loaded())

        compose.onNodeWithTag(OrderListTestTags.EMPTY).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.orders_empty_title)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.orders_browse_plans)).performClick()

        assertEquals(1, browsed)
    }

    @Test
    fun `orders that cannot be loaded say why and can be retried`() {
        render(OrderListUiState(isLoading = false, loadError = OrderError.NETWORK))

        compose.onNodeWithText(str(R.string.error_orders_network)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.orders_retry)).performClick()

        assertEquals(1, retries)
    }

    @Test
    fun `saved orders shown offline carry a note`() {
        render(loaded(pending).copy(refreshError = OrderError.NETWORK))

        compose.onNodeWithTag(OrderListTestTags.STALE).assertIsDisplayed()
        compose.onAllNodesWithTag(OrderListTestTags.ORDER_CARD).assertCountEquals(1)
    }
}
