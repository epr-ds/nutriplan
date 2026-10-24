package com.nutriplan.android.a11y

import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.screen.notifications.NotificationsScreenContent
import com.nutriplan.android.screen.notifications.NotificationsPreferencesScreenContent
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.model.NotificationPreferences
import com.nutriplan.shared.notifications.NotificationsError
import com.nutriplan.shared.notifications.NotificationsUiState
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * NTF-606: accessibility checks for the notification center (list) and preferences screens.
 *
 * Guards the labels, content descriptions and touch targets that TalkBack / VoiceOver need on the
 * surfaces shipped by NTF-506 / NTF-507 / NTF-509, so the a11y pass stays green after the
 * notification work landed. Runs on the JVM via Robolectric, so it is a deterministic guard without
 * an emulator.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class NotificationsAccessibilityTest {

    @get:Rule
    val compose = createComposeRule()

    private fun notification(id: String) = com.nutriplan.shared.data.model.Notification(
        id = id,
        userId = "user-1",
        title = "Order delivered",
        body = "Your order was delivered.",
        type = "order_delivered",
        isRead = false,
        createdAt = "2026-10-24T00:00:00Z",
    )

    @Test
    fun notification_content_title_is_a_heading_for_screen_readers() {
        compose.setContent {
            NutriPlanTheme {
                NotificationsScreenContent(
                    state = NotificationsUiState(isLoading = false),
                    onRefresh = {},
                    onRetry = {},
                    onMarkAsRead = {},
                    onNotificationClick = {},
                )
            }
        }

        compose.onNodeWithText("Notifications").assertIsDisplayed()
        compose.onNodeWithText("Notifications").assert(isHeading())
    }

    @Test
    fun notification_items_are_announced_with_content_descriptions() {
        compose.setContent {
            NutriPlanTheme {
                NotificationsScreenContent(
                    state = NotificationsUiState(
                        notifications = listOf(notification("n-1")),
                        isLoading = false,
                    ),
                    onRefresh = {},
                    onRetry = {},
                    onMarkAsRead = {},
                    onNotificationClick = {},
                )
            }
        }

        compose.onNodeWithText("Order delivered").assertIsDisplayed()
        compose.onNodeWithContentDescription("Order delivered, Your order was delivered.").assertExists()
    }

    @Test
    fun notification_error_is_displayed_and_retry_has_a_large_enough_touch_target() {
        compose.setContent {
            NutriPlanTheme {
                NotificationsScreenContent(
                    state = NotificationsUiState(
                        isLoading = false,
                        error = NotificationsError.NETWORK,
                    ),
                    onRefresh = {},
                    onRetry = {},
                    onMarkAsRead = {},
                    onNotificationClick = {},
                )
            }
        }

        compose.onNodeWithText("Can't reach the server. Check your connection and try again.").assertExists()
        compose.onNodeWithText("Retry").assertHeightIsAtLeast(48.dp)
    }

    @Test
    fun preference_toggles_are_labelled_and_have_sufficient_touch_targets() {
        val preferences = NotificationPreferences(
            pushEnabled = true,
            emailEnabled = true,
            mealReminders = true,
            orderUpdates = true,
            promotions = true,
        )

        compose.setContent {
            NutriPlanTheme {
                NotificationsPreferencesScreenContent(
                    preferences = preferences,
                    onBack = {},
                    onPushEnabled = {},
                    onMealRemindersEnabled = {},
                    onOrderUpdatesEnabled = {},
                    onPromotionsEnabled = {},
                    onEmailEnabled = {},
                    onQuietHoursChange = { _, _ -> },
                )
            }
        }

        compose.onNodeWithContentDescription("Push notifications").assertExists()
        compose.onNodeWithContentDescription("Meal plan reminders").assertExists()
        compose.onNodeWithContentDescription("Order updates").assertExists()
        compose.onNodeWithContentDescription("Promotions").assertExists()
        compose.onNodeWithContentDescription("Email notifications").assertExists()
        compose.onNodeWithContentDescription("Push notifications").assertHeightIsAtLeast(48.dp)
    }
}