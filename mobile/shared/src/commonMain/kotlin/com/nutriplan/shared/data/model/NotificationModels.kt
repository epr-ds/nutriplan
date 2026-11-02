package com.nutriplan.shared.data.model

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/** Notification entity as served by the Notification service feed page (NTF-602). */
@Serializable
data class Notification(
    val id: String,
    val userId: String? = null,
    val title: String? = null,
    val body: String? = null,
    val type: String? = null,
    val data: Map<String, String>? = null,
    val payload: Map<String, JsonElement>? = null,
    val channels: List<String>? = null,
    val status: String? = null,
    val createdAt: String? = null,
    val readAt: String? = null,
    val isRead: Boolean = false,
)

/** Unread count response from ``GET /notifications/unread-count``. */
@Serializable
data class UnreadCountResponse(
    val unreadCount: Int = 0,
)

/** One page of the notification feed, as served by ``GET /notifications`` (NTF-602). */
@Serializable
data class NotificationPage(
    val items: List<Notification>,
    val page: Int? = null,
    val limit: Int? = null,
    val unreadCount: Int? = null,
    val hasMore: Boolean? = null,
)

/** Notification preferences. */
@Serializable
data class NotificationPreferences(
    val pushEnabled: Boolean,
    val emailEnabled: Boolean,
    val mealReminders: Boolean,
    val orderUpdates: Boolean,
    val promotions: Boolean,
    val quietHoursStart: String? = null,
    val quietHoursEnd: String? = null,
)

/** A push token the app wants associated with the authenticated account (NTF-501). */
@Serializable
data class RegisterDevice(
    val platform: String,
    val token: String,
)

/** A stored push-device registration; the id is what the client uses to revoke it (NTF-501). */
@Serializable
data class RegisteredDevice(
    val id: String,
    val platform: String,
    val createdAt: String,
    val updatedAt: String,
)

/** Request to update notification preferences. */
@Serializable
data class UpdateNotificationPreferencesRequest(
    val pushEnabled: Boolean? = null,
    val emailEnabled: Boolean? = null,
    val mealReminders: Boolean? = null,
    val orderUpdates: Boolean? = null,
    val promotions: Boolean? = null,
    val quietHoursStart: String? = null,
    val quietHoursEnd: String? = null,
)
