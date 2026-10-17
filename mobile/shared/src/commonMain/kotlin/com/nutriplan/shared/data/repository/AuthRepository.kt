package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.local.TokenStorage
import com.nutriplan.shared.data.model.AuthResponse
import com.nutriplan.shared.data.model.LoginRequest
import com.nutriplan.shared.data.model.OAuthRequest
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
 * Manages token lifecycle (access + refresh). The default implementation keeps tokens in memory
 * and, when given a [TokenStorage], persists them in the platform's secure store.
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
     * Login with a third-party identity token (`POST /auth/oauth/{provider}`) and store the tokens.
     */
    suspend fun oauthLogin(provider: String, request: OAuthRequest): AuthResponse

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
 * Default implementation of [AuthRepository].
 *
 * Tokens are held in memory for fast access. When a [tokenStorage] is given (the app passes the
 * Keystore/Keychain-backed `SecureTokenStorage`), the session is restored from it on creation
 * and every change is written through, so the user stays signed in across launches.
 */
class InMemoryAuthRepository(
    private val tokenStorage: TokenStorage? = null,
) : AuthRepository {

    private var _accessToken: String? = null
    private var _refreshToken: String? = null

    init {
        // An unreadable store must never crash startup; the user simply has to log in again.
        runCatching { tokenStorage?.load() }.getOrNull()?.let { stored ->
            _accessToken = stored.accessToken
            _refreshToken = stored.refreshToken
        }
    }

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
                response.body<AuthResponse>().also { updateTokens(it.accessToken, it.refreshToken) }
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
                response.body<AuthResponse>().also { updateTokens(it.accessToken, it.refreshToken) }
            } else {
                throw ApiException.HttpError(
                    statusCode = response.status.value,
                    body = response.body<String>(),
                )
            }
        }
    }

    override suspend fun oauthLogin(provider: String, request: OAuthRequest): AuthResponse {
        return withContext(Dispatchers.IO) {
            val client = HttpClientProvider.client
            val response = client.post("/identity/v1/auth/oauth/$provider") {
                setBody(request)
            }
            if (response.status == HttpStatusCode.OK) {
                response.body<AuthResponse>().also { updateTokens(it.accessToken, it.refreshToken) }
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
        // If persisting fails the session still works until the app is closed.
        runCatching { tokenStorage?.save(accessToken, refreshToken) }
    }

    override fun clearTokens() {
        _accessToken = null
        _refreshToken = null
        runCatching { tokenStorage?.clear() }
    }
}
