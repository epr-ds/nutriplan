++ b/mobile/shared/src/commonMain/kotlin/com/nutriplan/shared/data/model/NotificationModels.kt
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
