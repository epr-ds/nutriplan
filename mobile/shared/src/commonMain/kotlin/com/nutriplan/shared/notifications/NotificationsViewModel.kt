package com.nutriplan.shared.notifications

import com.nutriplan.shared.data.model.Notification
import com.nutriplan.shared.data.model.NotificationPreferences
import com.nutriplan.shared.data.model.UnreadCountResponse
import com.nutriplan.shared.data.model.UpdateNotificationPreferencesRequest
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
 * whenever the list loads, so a pull-to-refresh also refreshes the badge. [preferences] is the
 * user's notification preferences (NTF-509) as the server holds them; the preferences screen reads
 * and updates it.
 */
data class NotificationsUiState(
    val notifications: List<Notification> = emptyList(),
    val isLoading: Boolean = true,
    val isRefreshing: Boolean = false,
    val error: NotificationsError? = null,
    val unreadCount: Int = 0,
    val preferences: NotificationPreferences? = null,
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
        val previous = state.value
        _state.update { state ->
            val marked = state.notifications.firstOrNull { it.id == notificationId }
            val wasUnread = marked != null && !marked.isRead
            state.copy(
                notifications = state.notifications.map { notification ->
                    if (notification.id == notificationId) notification.copy(isRead = true) else notification
                },
                // NTF-801: marking one notification read moves the unread badge with it.
                unreadCount = if (wasUnread) state.unreadCount - 1 else state.unreadCount,
            )
        }
        try {
            repository.markAsRead(notificationId)
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(error = e.toNotificationsError()) }
            // NTF-802: the optimistic mark has not been confirmed yet; roll it back so a failed
            // confirmation does not leave a read state (and badge decrement) the server rejected.
            _state.value = previous
        }
    }

    /** Load the user's notification preferences (NTF-509) into the state; called by the preferences screen. */
    suspend fun loadPreferences() {
        try {
            val preferences = repository.getPreferences()
            _state.update { it.copy(preferences = preferences) }
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(error = e.toNotificationsError()) }
        }
    }

    /**
     * Update the notification preferences (NTF-509): optimistically apply [request] to the local
     * preferences, then confirm through the repository; on failure roll the previous preferences
     * back so the UI does not keep the optimistic value.
     */
    suspend fun updatePreferences(request: UpdateNotificationPreferencesRequest) {
        val previous = state.value.preferences
        _state.update { it.copy(preferences = previous?.withRequest(request) ?: request.toPreferences()) }
        try {
            val updated = repository.updatePreferences(request)
            _state.update { it.copy(preferences = updated) }
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(preferences = previous) }
        }
    }

    /** Turn the push channel (master switch) on or off (NTF-509). */
    suspend fun updatePushEnabled(enabled: Boolean) =
        updatePreferences(UpdateNotificationPreferencesRequest(pushEnabled = enabled))

    /** Turn a per-type push switch (meal reminders / order updates / promotions) on or off (NTF-509). */
    suspend fun updateMealReminders(enabled: Boolean) = updatePreferences(UpdateNotificationPreferencesRequest(mealReminders = enabled))

    suspend fun updateOrderUpdates(enabled: Boolean) = updatePreferences(UpdateNotificationPreferencesRequest(orderUpdates = enabled))

    suspend fun updatePromotions(enabled: Boolean) = updatePreferences(UpdateNotificationPreferencesRequest(promotions = enabled))

    /** Turn the email channel on or off (NTF-509). */
    suspend fun updateEmailEnabled(enabled: Boolean) = updatePreferences(UpdateNotificationPreferencesRequest(emailEnabled = enabled))

    /** Set the quiet-hours window as `HH:mm` strings; null clears it (NTF-509). */
    suspend fun updateQuietHours(start: String?, end: String?) =
        updatePreferences(UpdateNotificationPreferencesRequest(quietHoursStart = start, quietHoursEnd = end))

    /** Forget the error, e.g. when the user retries from the screen. */
    fun clearError() {
        _state.update { it.copy(error = null) }
    }

    /** Forget the in-memory list (on sign-out). */
    fun reset() {
        _state.value = NotificationsUiState()
    }

    /** The current UI state, for callers that read rather than observe it (e.g. the SwiftUI bridge). */
    fun currentState(): NotificationsUiState = _state.value
}

/** Apply only the fields a (partial) update request carries onto the current preferences. */
private fun NotificationPreferences.withRequest(request: UpdateNotificationPreferencesRequest): NotificationPreferences =
    copy(
        pushEnabled = request.pushEnabled ?: this.pushEnabled,
        emailEnabled = request.emailEnabled ?: this.emailEnabled,
        mealReminders = request.mealReminders ?: this.mealReminders,
        orderUpdates = request.orderUpdates ?: this.orderUpdates,
        promotions = request.promotions ?: this.promotions,
        quietHoursStart = request.quietHoursStart ?: this.quietHoursStart,
        quietHoursEnd = request.quietHoursEnd ?: this.quietHoursEnd,
    )

/** Default preferences for a request that does not carry every field. */
private fun UpdateNotificationPreferencesRequest.toPreferences(): NotificationPreferences =
    NotificationPreferences(
        pushEnabled = pushEnabled ?: true,
        emailEnabled = emailEnabled ?: true,
        mealReminders = mealReminders ?: true,
        orderUpdates = orderUpdates ?: true,
        promotions = promotions ?: true,
        quietHoursStart = quietHoursStart,
        quietHoursEnd = quietHoursEnd,
    )
