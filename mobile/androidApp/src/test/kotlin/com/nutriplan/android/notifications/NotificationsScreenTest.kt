package com.nutriplan.android.notifications

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.screen.notifications.NotificationsScreenContent
import com.nutriplan.android.screen.notifications.NotificationsTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.model.Notification
import com.nutriplan.shared.notifications.NotificationsError
import com.nutriplan.shared.notifications.NotificationsUiState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * NTF-506: the in-app notification center renders its states and reacts to a tap.
 *
 * Runs on the JVM via Robolectric, so it is a deterministic guard without an emulator.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class NotificationsScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int): String = context.getString(id)

    private fun notification(id: String) = Notification(
        id = id,
        userId = "user-1",
        title = "Order delivered",
        body = "Your order was delivered.",
        type = "order_delivered",
        isRead = false,
        createdAt = "2026-10-24T00:00:00Z",
    )

    private fun render(
        state: NotificationsUiState,
        onRefresh: () -> Unit = {},
        onRetry: () -> Unit = {},
        onMarkAsRead: (String) -> Unit = {},
        onNotificationClick: (String) -> Unit = {},
    ) {
        compose.setContent {
            NutriPlanTheme {
                NotificationsScreenContent(
                    state = state,
                    onRefresh = onRefresh,
                    onRetry = onRetry,
                    onMarkAsRead = onMarkAsRead,
                    onNotificationClick = onNotificationClick,
                )
            }
        }
    }

    @Test
    fun `first load shows a labelled progress indicator`() {
        render(NotificationsUiState())

        compose.onNodeWithTag(NotificationsTestTags.LOADING).assertIsDisplayed()
        compose.onNodeWithContentDescription(str(R.string.cd_notifications_loading)).assertExists()
    }

    @Test
    fun `an empty list shows the empty state`() {
        render(NotificationsUiState(isLoading = false))

        compose.onNodeWithText(str(R.string.notification_empty_title)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.notification_empty_description)).assertIsDisplayed()
    }

    @Test
    fun `failing with nothing loaded shows an error with retry`() {
        var retried = 0
        render(
            NotificationsUiState(isLoading = false, error = NotificationsError.NETWORK),
            onRetry = { retried++ },
        )

        compose.onNodeWithText(str(R.string.error_notifications_network)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.notifications_retry)).performClick()
        assertEquals(1, retried)
    }

    @Test
    fun `the notification list marks a tap as read and follows the deep link`() {
        val marked = mutableListOf<String>()
        val deepLinks = mutableListOf<String>()
        render(
            NotificationsUiState(
                notifications = listOf(notification("n-1")),
                isLoading = false,
            ),
            onMarkAsRead = { marked += it },
            onNotificationClick = { deepLinks += it },
        )

        compose.onNodeWithText("Order delivered").assertIsDisplayed()
        compose.onNodeWithText("Your order was delivered.").assertIsDisplayed()

        compose.onNodeWithText("Order delivered").performClick()
        assertEquals(listOf("n-1"), marked)
        assertTrue(deepLinks.isEmpty())
    }

    @Test
    fun `the center title is a heading for screen readers`() {
        render(NotificationsUiState())

        compose.onNodeWithText(str(R.string.notification_center_title)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.notification_center_title)).assert(isHeading())
    }
}