package com.nutriplan.shared.notifications

import com.nutriplan.shared.data.model.Notification
import com.nutriplan.shared.data.model.UnreadCountResponse
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.toApiFailure
import com.nutriplan.shared.data.repository.NotificationRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/** Why the notification list could not be loaded. Locale-neutral: each platform maps these codes to its own localized microcopy (NTF-506 convention). */
enum class NotificationsError {
    /** The device could not reach the server. */
    NETWORK,

    /** The server failed (HTTP 5xx). */
    SERVER_PROBLEM,

    /** The server rejected the session (HTTP 401): the user has to sign in again. */
    SESSION_EXPIRED,

    /** Anything else. */
    UNKNOWN,
}

/**
 * Observable state of the user's in-app notification list (NTF-506).
 *
 * [notifications] is the loaded list, most recent first as the server sends it; the screen owns the
 * list while it is visible. [unreadCount] is what the entry-point badge shows; it is refreshed
 * whenever the list loads, so a pull-to-refresh also refreshes the badge.
 */
data class NotificationsUiState(
    val notifications: List<Notification> = emptyList(),
    val isLoading: Boolean = true,
    val isRefreshing: Boolean = false,
    val error: NotificationsError? = null,
    val unreadCount: Int = 0,
) {
    /** Whether the user has anything unread, for the entry-point badge. */
    val hasUnread: Boolean get() = unreadCount > 0

    /** Whether the user has nothing to show: not loading, no error and no notifications. */
    val isEmpty: Boolean get() = !isLoading && error == null && notifications.isEmpty()
}

/** Maps a thrown repository failure to the locale-neutral [NotificationsError]. */
fun Throwable.toNotificationsError(): NotificationsError = when (toApiFailure()) {
    ApiFailure.OFFLINE -> NotificationsError.NETWORK
    ApiFailure.SERVER -> NotificationsError.SERVER_PROBLEM
    ApiFailure.SESSION_EXPIRED -> NotificationsError.SESSION_EXPIRED
    else -> NotificationsError.UNKNOWN
}

/**
 * Shared logic of the in-app notification list used by the Compose and SwiftUI screens (NTF-506):
 * loading, pull-to-refresh, marking a notification as read, and the loading/error state.
 *
 * The functions are `suspend` so the UI owns the coroutine scope; [CancellationException] is
 * rethrown so leaving the screen cancels cleanly.
 */
class NotificationsViewModel(
    private val repository: NotificationRepository,
) {

    private val _state = MutableStateFlow(NotificationsUiState())
    val state: StateFlow<NotificationsUiState> = _state.asStateFlow()

    /** First load, or retry after a failure; keeps the visible list while loading. */
    suspend fun load() {
        _state.update { it.copy(isLoading = it.notifications.isEmpty(), error = null) }
        fetch()
    }

    /** Pull-to-refresh: keeps the current list visible while the request runs. */
    suspend fun refresh() {
        _state.update { it.copy(isRefreshing = true, error = null) }
        fetch()
    }

    private suspend fun fetch() {
        try {
            val notifications = repository.getNotifications()
            val unread = repository.getUnreadCount().count
            _state.update {
                it.copy(
                    notifications = notifications,
                    unreadCount = unread,
                    isLoading = false,
                    isRefreshing = false,
                )
            }
        } catch (e: CancellationException) {
            _state.update { it.copy(isLoading = false, isRefreshing = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update {
                it.copy(
                    isLoading = false,
                    isRefreshing = false,
                    error = e.toNotificationsError(),
                )
            }
        }
    }

    /** Mark one notification as read: optimistically on the local copy, then confirm. */
    suspend fun markAsRead(notificationId: String) {
        _state.update { state ->
            state.copy(
                notifications = state.notifications.map { notification ->
                    if (notification.id == notificationId) notification.copy(isRead = true) else notification
                },
            )
        }
        try {
            repository.markAsRead(notificationId)
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(error = e.toNotificationsError()) }
        }
    }

    /** Forget the error, e.g. when the user retries from the screen. */
    fun clearError() {
        _state.update { it.copy(error = null) }
    }

    /** Forget the in-memory list (on sign-out). */
    fun reset() {
        _state.value = NotificationsUiState()
    }
}