package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.model.AvatarUploadUrlRequest
import com.nutriplan.shared.data.model.AvatarUploadUrlResponse
import com.nutriplan.shared.data.model.UpdateDietaryPreferencesRequest
import com.nutriplan.shared.data.model.UpdateProfileRequest
import com.nutriplan.shared.data.model.UserProfile
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
 * Repository for identity-related API operations.
 *
 * Covers user profile management, dietary preferences, and avatar operations.
 */
interface IdentityRepository {

    /** Get the current user's profile. */
    suspend fun getMe(): UserProfile

    /** Update the current user's profile. */
    suspend fun updateMe(request: UpdateProfileRequest): UserProfile

    /** Update the current user's dietary preferences. */
    suspend fun updateDietaryPreferences(request: UpdateDietaryPreferencesRequest)

    /** Get a presigned URL for avatar upload. */
    suspend fun getAvatarUploadUrl(request: AvatarUploadUrlRequest): AvatarUploadUrlResponse

    /** Confirm avatar upload by setting the avatar URL. */
    suspend fun setAvatar(avatarUrl: String)
}

/**
 * Identity service API client implementation.
 */
class IdentityRepositoryImpl : IdentityRepository {

    private val client = HttpClientProvider.client

    override suspend fun getMe(): UserProfile {
        return withContext(Dispatchers.IO) {
            val response = client.get("${ApiConfig.IDENTITY}/users/me")
            handleResponse(response)
        }
    }

    override suspend fun updateMe(request: UpdateProfileRequest): UserProfile {
        return withContext(Dispatchers.IO) {
            val response = client.put("${ApiConfig.IDENTITY}/users/me") {
                setBody(request)
            }
            handleResponse(response)
        }
    }

    override suspend fun updateDietaryPreferences(request: UpdateDietaryPreferencesRequest) {
        withContext(Dispatchers.IO) {
            val response = client.put("${ApiConfig.IDENTITY}/users/me/dietary-preferences") {
                setBody(request)
            }
            if (response.status != HttpStatusCode.OK && response.status != HttpStatusCode.Accepted) {
                throw ApiException.HttpError(
                    statusCode = response.status.value,
                    body = response.body<String>(),
                )
            }
        }
    }

    override suspend fun getAvatarUploadUrl(request: AvatarUploadUrlRequest): AvatarUploadUrlResponse {
        return withContext(Dispatchers.IO) {
            val response = client.post("${ApiConfig.IDENTITY}/users/me/avatar-upload-url") {
                setBody(request)
            }
            handleResponse(response)
        }
    }

    override suspend fun setAvatar(avatarUrl: String) {
        withContext(Dispatchers.IO) {
            val response = client.put("${ApiConfig.IDENTITY}/users/me/avatar") {
                setBody(mapOf("avatarUrl" to avatarUrl))
            }
            if (response.status != HttpStatusCode.OK && response.status != HttpStatusCode.Accepted) {
                throw ApiException.HttpError(
                    statusCode = response.status.value,
                    body = response.body<String>(),
                )
            }
        }
    }

    /**
     * Get the JWKS (JSON Web Key Set) for JWT verification.
     */
    suspend fun getJwks(): Map<String, Any> {
        return withContext(Dispatchers.IO) {
            val client = HttpClientProvider.client
            val response = client.get("${ApiConfig.IDENTITY}/auth/jwks")
            @Suppress("UNCHECKED_CAST")
            response.body() as Map<String, Any>
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
}
