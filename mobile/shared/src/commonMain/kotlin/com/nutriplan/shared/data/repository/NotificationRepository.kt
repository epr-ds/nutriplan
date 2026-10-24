package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.model.Notification
import com.nutriplan.shared.data.model.NotificationPreferences
import com.nutriplan.shared.data.model.RegisterDevice
import com.nutriplan.shared.data.model.RegisteredDevice
import com.nutriplan.shared.data.model.UnreadCountResponse
import com.nutriplan.shared.data.model.UpdateNotificationPreferencesRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.HttpClientProvider
import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.http.HttpStatusCode
import io.ktor.http.isSuccess
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.withContext

/**
 * Repository for notification-related API operations.
 *
 * Covers notification listing, read status, device registration, and preferences.
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

    /**
     * Register or refresh a push device token (`POST /notifications/devices`). The token is
     * the registration's identity, so repeating it refreshes and returns the same device id; a
     * token that already belongs to another account is moved to the caller.
     */
    suspend fun registerDevice(platform: String, token: String): RegisteredDevice

    /** Revoke a push device registration (`DELETE /notifications/devices/{deviceId}`). */
    suspend fun revokeDevice(deviceId: String)
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
            val response = client.post("${ApiConfig.NOTIFICATION}/notifications/$notificationId/read") { }
            if (response.status != HttpStatusCode.OK && response.status != HttpStatusCode.Accepted) {
                throw ApiException.HttpError(
                    statusCode = response.status.value,
                    body = response.body<String>(),
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

    override suspend fun registerDevice(platform: String, token: String): RegisteredDevice {
        return withContext(Dispatchers.IO) {
            val response = client.post("${ApiConfig.NOTIFICATION}/notifications/devices") {
                setBody(RegisterDevice(platform = platform, token = token))
            }
            handleResponse(response)
        }
    }

    override suspend fun revokeDevice(deviceId: String) {
        withContext(Dispatchers.IO) {
            val response = client.delete("${ApiConfig.NOTIFICATION}/notifications/devices/$deviceId")
            if (!response.status.isSuccess()) {
                throw ApiException.HttpError(
                    statusCode = response.status.value,
                    body = response.body<String>(),
                )
            }
        }
    }

    private suspend inline fun <reified T> handleResponse(response: io.ktor.client.statement.HttpResponse): T {
        return when (response.status) {
            HttpStatusCode.OK, HttpStatusCode.Created -> response.body()
            HttpStatusCode.Unauthorized -> throw ApiException.create(
                message = "Unauthorized. Please log in again.",
                code = ApiException.Code.UNAUTHORIZED,
            )
            HttpStatusCode.Forbidden -> throw ApiException.create(
                message = "Forbidden. You don't have permission.",
                code = ApiException.Code.FORBIDDEN,
            )
            HttpStatusCode.NotFound -> throw ApiException.create(
                message = "Resource not found.",
                code = ApiException.Code.NOT_FOUND,
            )
            else -> throw ApiException.HttpError(
                statusCode = response.status.value,
                body = response.body<String>(),
            )
        }
    }

    private suspend inline fun <reified T> handleListResponse(response: io.ktor.client.statement.HttpResponse): List<T> {
        return when (response.status) {
            HttpStatusCode.OK -> response.body()
            HttpStatusCode.Unauthorized -> throw ApiException.create(
                message = "Unauthorized. Please log in again.",
                code = ApiException.Code.UNAUTHORIZED,
            )
            else -> throw ApiException.HttpError(
                statusCode = response.status.value,
                body = response.body<String>(),
            )
        }
    }
}