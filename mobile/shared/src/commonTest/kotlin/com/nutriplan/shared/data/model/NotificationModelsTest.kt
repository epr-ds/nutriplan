package com.nutriplan.shared.data.model

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class NotificationModelsTest {

    @Test
    fun `Notification creates correctly`() {
        val notification = Notification(
            id = "notif-123",
            userId = "user-1",
            title = "Meal Plan Ready",
            body = "Your meal plan is ready to view",
            type = "meal_plan",
            isRead = false,
            createdAt = "2024-01-15T10:00:00Z",
        )
        assertEquals("notif-123", notification.id)
        assertEquals("Meal Plan Ready", notification.title)
        assertEquals("Your meal plan is ready to view", notification.body)
        assertEquals("meal_plan", notification.type)
        assertEquals(false, notification.isRead)
        assertNull(notification.readAt)
        assertEquals("2024-01-15T10:00:00Z", notification.createdAt)
    }

    @Test
    fun `UnreadCountResponse creates correctly`() {
        assertEquals(5, UnreadCountResponse(count = 5).count)
    }

    @Test
    fun `NotificationPreferences creates correctly`() {
        val prefs = NotificationPreferences(
            pushEnabled = true,
            emailEnabled = false,
            mealReminders = true,
            orderUpdates = true,
            promotions = false,
            quietHoursStart = "22:00",
            quietHoursEnd = "07:00",
        )
        assertEquals(true, prefs.pushEnabled)
        assertEquals(false, prefs.emailEnabled)
        assertEquals("22:00", prefs.quietHoursStart)
    }

    @Test
    fun `UpdateNotificationPreferencesRequest only carries provided fields`() {
        val request = UpdateNotificationPreferencesRequest(pushEnabled = false)
        assertEquals(false, request.pushEnabled)
        assertNull(request.emailEnabled)
        assertNull(request.quietHoursStart)
    }
}