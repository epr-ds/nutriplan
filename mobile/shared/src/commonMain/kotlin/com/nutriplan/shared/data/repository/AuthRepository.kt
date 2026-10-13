++ b/mobile/shared/src/commonMain/kotlin/com/nutriplan/shared/data/repository/AuthRepository.kt
package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.model.AuthResponse
import com.nutriplan.shared.data.model.LoginRequest
import com.nutriplan.shared.data.model.RefreshRequest
import com.nutriplan.shared.data.model.RegisterRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.HttpClientProvider
import io.ktor.client.call.body
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.HttpStatusCode
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.withContext

/**
 * Repository for authentication operations.
 *
 * Manages token lifecycle (access + refresh) using an in-memory store.
 * Tokens are not persisted; callers should handle persistence at a higher level.
 */
interface AuthRepository {

    /** Current access token, or null if not authenticated. */
    val currentAccessToken: String?

    /** Current refresh token, or null if not authenticated. */
    val currentRefreshToken: String?

    /** Whether the user currently has valid tokens. */
    val isAuthenticated: Boolean

    /**
     * Register a new user and store the returned tokens.
     */
    suspend fun register(request: RegisterRequest): AuthResponse

    /**
     * Login with email/password and store the returned tokens.
     */
    suspend fun login(request: LoginRequest): AuthResponse

    /**
     * Refresh the access token using the current refresh token.
     */
    suspend fun refreshToken(refreshToken: String): AuthResponse

    /**
     * Update stored tokens after a refresh or login.
     */
    fun updateTokens(accessToken: String, refreshToken: String)

    /**
     * Clear all stored tokens (logout).
     */
    fun clearTokens()

    companion object {
        private val _instance: AuthRepository = InMemoryAuthRepository()

        val instance: AuthRepository
            get() = _instance
    }
}

/**
 * In-memory implementation of [AuthRepository].
 *
 * Tokens are stored in memory and cleared on logout.
 * For production use, consider persisting tokens in secure storage
 * (e.g., Android Keystore / iOS Keychain) at the app layer.
 */
class InMemoryAuthRepository : AuthRepository {

    private var _accessToken: String? = null
    private var _refreshToken: String? = null

    override val currentAccessToken: String?
        get() = _accessToken

    override val currentRefreshToken: String?
        get() = _refreshToken

    override val isAuthenticated: Boolean
        get() = _accessToken != null && _accessToken!!.isNotEmpty()

    override suspend fun register(request: RegisterRequest): AuthResponse {
        return withContext(Dispatchers.IO) {
            val client = HttpClientProvider.client
            val response = client.post("/identity/v1/auth/register") {
                setBody(request)
            }
            if (response.status == HttpStatusCode.Created || response.status == HttpStatusCode.OK) {
                response.body()
            } else {
                throw ApiException.HttpError(
                    statusCode = response.status.value,
                    body = response.body<String>(),
                )
            }
        }
    }

    override suspend fun login(request: LoginRequest): AuthResponse {
        return withContext(Dispatchers.IO) {
            val client = HttpClientProvider.client
            val response = client.post("/identity/v1/auth/login") {
                setBody(request)
            }
            if (response.status == HttpStatusCode.OK) {
                response.body()
            } else {
                throw ApiException.HttpError(
                    statusCode = response.status.value,
                    body = response.body<String>(),
                )
            }
        }
    }

    override suspend fun refreshToken(refreshToken: String): AuthResponse {
        return withContext(Dispatchers.IO) {
            val client = HttpClientProvider.client
            val response = client.post("/identity/v1/auth/refresh") {
                setBody(RefreshRequest(refreshToken))
            }
            if (response.status == HttpStatusCode.OK) {
                response.body()
            } else {
                throw ApiException.HttpError(
                    statusCode = response.status.value,
                    body = response.body<String>(),
                )
            }
        }
    }

    override fun updateTokens(accessToken: String, refreshToken: String) {
        _accessToken = accessToken
        _refreshToken = refreshToken
    }

    override fun clearTokens() {
        _accessToken = null
        _refreshToken = null
    }
}
