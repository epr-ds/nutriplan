package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.model.Notification
import com.nutriplan.shared.data.model.NotificationPreferences
import com.nutriplan.shared.data.model.UnreadCountResponse
import com.nutriplan.shared.data.model.UpdateNotificationPreferencesRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.HttpClientProvider
import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.http.HttpStatusCode
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.withContext

/**
 * Repository for notification-related API operations.
 *
 * Covers notification listing, read status, and preferences.
 */
interface NotificationRepository {

    /** List notifications. */
    suspend fun getNotifications(): List<Notification>

    /** Get the unread notification count. */
    suspend fun getUnreadCount(): UnreadCountResponse

    /** Mark a notification as read. */
    suspend fun markAsRead(notificationId: String)

    /** Get notification preferences. */
    suspend fun getPreferences(): NotificationPreferences

    /** Update notification preferences. */
    suspend fun updatePreferences(request: UpdateNotificationPreferencesRequest): NotificationPreferences
}

/**
 * Notification service API client implementation.
 */
class NotificationRepositoryImpl : NotificationRepository {

    private val client = HttpClientProvider.client

    override suspend fun getNotifications(): List<Notification> {
        return withContext(Dispatchers.IO) {
            val response = client.get("${ApiConfig.NOTIFICATION}/notifications")
            handleListResponse(response)
        }
    }

    override suspend fun getUnreadCount(): UnreadCountResponse {
        return withContext(Dispatchers.IO) {
            val response = client.get("${ApiConfig.NOTIFICATION}/notifications/unread-count")
            handleResponse(response)
        }
    }

    override suspend fun markAsRead(notificationId: String) {
        withContext(Dispatchers.IO) {
            val response = client.post("${ApiConfig.NOTIFICATION}/notifications/$notificationId/read") {}
            if (response.status != HttpStatusCode.OK && response.status != HttpStatusCode.Accepted) {
                throw ApiException.HttpError(
                    statusCode = response.status.value,
                    body = response.text,
                )
            }
        }
    }

    override suspend fun getPreferences(): NotificationPreferences {
        return withContext(Dispatchers.IO) {
            val response = client.get("${ApiConfig.NOTIFICATION}/notifications/preferences")
            handleResponse(response)
        }
    }

    override suspend fun updatePreferences(request: UpdateNotificationPreferencesRequest): NotificationPreferences {
        return withContext(Dispatchers.IO) {
            val response = client.put("${ApiConfig.NOTIFICATION}/notifications/preferences") {
                setBody(request)
            }
            handleResponse(response)
        }
    }

    private suspend inline fun <reified T> handleResponse(response: io.ktor.client.statement.HttpResponse): T {
        return when (response.status) {
            HttpStatusCode.OK, HttpStatusCode.Created -> response.body()
            HttpStatusCode.Unauthorized -> throw ApiException(
                message = "Unauthorized. Please log in again.",
                code = ApiException.Code.UNAUTHORIZED,
            )
            HttpStatusCode.Forbidden -> throw ApiException(
                message = "Forbidden. You don't have permission.",
                code = ApiException.Code.FORBIDDEN,
            )
            HttpStatusCode.NotFound -> throw ApiException(
                message = "Resource not found.",
                code = ApiException.Code.NOT_FOUND,
            )
            else -> throw ApiException.HttpError(
                statusCode = response.status.value,
                body = response.text,
            )
        }
    }

    private suspend inline fun <reified T> handleListResponse(response: io.ktor.client.statement.HttpResponse): List<T> {
        return when (response.status) {
            HttpStatusCode.OK -> response.body()
            HttpStatusCode.Unauthorized -> throw ApiException(
                message = "Unauthorized. Please log in again.",
                code = ApiException.Code.UNAUTHORIZED,
            )
            else -> throw ApiException.HttpError(
                statusCode = response.status.value,
                body = response.text,
            )
        }
    }
}
