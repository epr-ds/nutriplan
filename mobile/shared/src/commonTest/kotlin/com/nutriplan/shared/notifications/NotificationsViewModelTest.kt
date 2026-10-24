package com.nutriplan.shared.notifications

import com.nutriplan.shared.data.model.Notification
import com.nutriplan.shared.data.model.NotificationPreferences
import com.nutriplan.shared.data.model.RegisteredDevice
import com.nutriplan.shared.data.model.UnreadCountResponse
import com.nutriplan.shared.data.model.UpdateNotificationPreferencesRequest
import com.nutriplan.shared.data.repository.NotificationRepository
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * NTF-506: the in-app notification list — loading, error, mark-read and reset.
 */
class NotificationsViewModelTest {

    private class FakeNotificationRepository : NotificationRepository {
        var notifications: List<Notification> = emptyList()
        var unreadCount: Int = 0
        var failure: Throwable? = null
        val markedReads = mutableListOf<String>()

        override suspend fun getNotifications(): List<Notification> {
            failure?.let { throw it }
            return notifications
        }

        override suspend fun getUnreadCount(): UnreadCountResponse {
            failure?.let { throw it }
            return UnreadCountResponse(unreadCount)
        }

        override suspend fun markAsRead(notificationId: String) {
            markedReads += notificationId
        }

        override suspend fun getPreferences(): NotificationPreferences = error("unused")

        override suspend fun updatePreferences(request: UpdateNotificationPreferencesRequest): NotificationPreferences = error("unused")

        override suspend fun registerDevice(platform: String, token: String): RegisteredDevice = error("unused")

        override suspend fun revokeDevice(deviceId: String) = Unit
    }

    private val repository = FakeNotificationRepository()

    private fun notification(id: String) = Notification(
        id = id,
        userId = "user-1",
        title = "Order delivered",
        body = "Your order was delivered.",
        type = "order_delivered",
        isRead = false,
        createdAt = "2026-10-24T00:00:00Z",
    )

    @AfterTest
    fun tearDown() {
        repository.notifications = emptyList()
        repository.unreadCount = 0
        repository.failure = null
        repository.markedReads.clear()
    }

    @Test
    fun `load stores the list and the unread count`() = runTest {
        repository.notifications = listOf(notification("n-1"))
        repository.unreadCount = 2

        val viewModel = NotificationsViewModel(repository)

        viewModel.load()

        val state = viewModel.state.value
        assertEquals(1, state.notifications.size)
        assertEquals("n-1", state.notifications.first().id)
        assertEquals(2, state.unreadCount)
        assertTrue(state.hasUnread)
        assertFalse(state.isLoading)
        assertNull(state.error)
        assertFalse(state.isEmpty)
    }

    @Test
    fun `load maps a failure onto the error state`() = runTest {
        repository.failure = RuntimeException("boom")

        val viewModel = NotificationsViewModel(repository)

        viewModel.load()

        val state = viewModel.state.value
        assertFalse(state.isLoading)
        assertEquals(NotificationsError.UNKNOWN, state.error)
        assertFalse(state.isEmpty)
    }

    @Test
    fun `markAsRead confirms through the repository and flags the local copy`() = runTest {
        repository.notifications = listOf(notification("n-1"))

        val viewModel = NotificationsViewModel(repository)

        viewModel.markAsRead("n-1")

        assertEquals(listOf("n-1"), repository.markedReads)
        assertTrue(viewModel.state.value.notifications.first().isRead)
    }

    @Test
    fun `reset clears the in-memory list`() = runTest {
        repository.notifications = listOf(notification("n-1"))
        val viewModel = NotificationsViewModel(repository)

        viewModel.reset()

        assertTrue(viewModel.state.value.notifications.isEmpty())
    }
}