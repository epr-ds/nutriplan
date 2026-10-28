package com.nutriplan.android.a11y

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.screen.orders.OrderDetailScreenContent
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.commerce.OrderDetailUiState
import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.Money
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderAddress
import com.nutriplan.shared.data.model.OrderItem
import com.nutriplan.shared.data.model.OrderStatusChange
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * COM-808: screen-reader regression checks for the commerce checkout / payment / order UI.
 *
 * The backend half of the COM-808 accessibility pass gates the wire vocabulary the screen-reader
 * cues map onto (see the commerce status vocabulary gate). This module guards the Compose side the
 * same way: the commerce screens must announce what a screen reader (TalkBack / VoiceOver) needs,
 * including the in-flight states, so the a11y pass cannot silently regress on the client while the
 * backend vocabulary gate holds. Runs on the JVM via Robolectric, so the checks are deterministic
 * without an emulator.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2400dp", application = TestApplication::class)
class CommerceA11yTest {

    @get:Rule
    val compose = createComposeRule()

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

    @Test
    fun `order detail cancelling indicator is announced to screen readers`() {
        compose.setContent {
            NutriPlanTheme {
                OrderDetailScreenContent(
                    state = OrderDetailUiState(isLoading = false, order = order, isCancelling = true),
                    onBack = {},
                    onRetry = {},
                    onRequestCancel = {},
                    onConfirmCancel = {},
                    onDismissCancel = {},
                    onDismissCancelError = {},
                )
            }
        }
        compose.waitForIdle()
        compose.onNodeWithContentDescription("Loading the order").assertIsDisplayed()
    }
}