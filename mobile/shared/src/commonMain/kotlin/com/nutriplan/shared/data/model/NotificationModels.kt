package com.nutriplan.shared.data.model

import kotlinx.serialization.Serializable

/** Notification entity. */
@Serializable
data class Notification(
    val id: String,
    val userId: String,
    val title: String,
    val body: String,
    val type: String,
    val data: Map<String, String>? = null,
    val isRead: Boolean,
    val readAt: String? = null,
    val createdAt: String? = null,
)

/** Unread count response. */
@Serializable
data class UnreadCountResponse(
    val count: Int,
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
