package com.nutriplan.shared.data.model

import kotlin.test.Test
import kotlin.test.assertEquals

class NotificationModelsTest {

    @Test
    fun `NotificationQuery creates correctly`() {
        val query = NotificationQuery(
            unreadOnly = true,
            limit = 20,
            offset = 0
        )
        assertEquals(true, query.unreadOnly)
        assertEquals(20, query.limit)
        assertEquals(0, query.offset)
    }

    @Test
    fun `MarkReadRequest creates correctly`() {
        val request = MarkReadRequest(
            notificationIds = listOf("notif-1", "notif-2", "notif-3")
        )
        assertEquals(3, request.notificationIds.size)
        assertEquals("notif-1", request.notificationIds[0])
    }

    @Test
    fun `Notification creates correctly`() {
        val notification = Notification(
            id = "notif-123",
            title = "Meal Plan Ready",
            message = "Your meal plan is ready to view",
            type = "meal_plan",
            isRead = false,
            createdAt = "2024-01-15T10:00:00Z"
        )
        assertEquals("notif-123", notification.id)
        assertEquals("Meal Plan Ready", notification.title)
        assertEquals("Your meal plan is ready to view", notification.message)
        assertEquals("meal_plan", notification.type)
        assertEquals(false, notification.isRead)
        assertEquals("2024-01-15T10:00:00Z", notification.createdAt)
    }
}
