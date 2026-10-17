package com.nutriplan.shared.session

import com.nutriplan.shared.data.model.AuthResponse
import com.nutriplan.shared.data.model.DietaryPreferences
import com.nutriplan.shared.data.model.LoginRequest
import com.nutriplan.shared.data.model.OAuthRequest
import com.nutriplan.shared.data.model.RegisterRequest
import com.nutriplan.shared.data.model.UserProfile
import com.nutriplan.shared.data.repository.AuthRepository

/** Builds an [AuthResponse] for the given onboarding completion state. */
internal fun authResponse(
    onboardingComplete: Boolean,
    accessToken: String = "access-1",
    refreshToken: String = "refresh-1",
): AuthResponse = AuthResponse(
    accessToken = accessToken,
    refreshToken = refreshToken,
    expiresIn = 900,
    user = UserProfile(
        id = "u1",
        email = "ana@example.com",
        name = "Ana",
        dietaryPreferences = if (onboardingComplete) DietaryPreferences(dietType = "omnivore") else null,
    ),
)

/**
 * In-memory [AuthRepository] for session tests.
 *
 * By default every credential exchange succeeds with [response]; set [error] to make them throw.
 * Token mutations are recorded so tests can assert the stored session.
 */
internal class FakeAuthRepository(
    private val response: AuthResponse = authResponse(onboardingComplete = false),
    private val error: Throwable? = null,
    initialAccessToken: String? = null,
) : AuthRepository {

    var accessToken: String? = initialAccessToken
        private set
    var refreshToken: String? = null
        private set
    var lastOAuthProvider: String? = null
        private set
    var lastOAuthRequest: OAuthRequest? = null
        private set

    override val currentAccessToken: String? get() = accessToken
    override val currentRefreshToken: String? get() = refreshToken
    override val isAuthenticated: Boolean get() = accessToken != null

    override suspend fun register(request: RegisterRequest): AuthResponse = respond()

    override suspend fun login(request: LoginRequest): AuthResponse = respond()

    override suspend fun oauthLogin(provider: String, request: OAuthRequest): AuthResponse {
        lastOAuthProvider = provider
        lastOAuthRequest = request
        return respond()
    }

    override suspend fun refreshToken(refreshToken: String): AuthResponse = respond()

    override fun updateTokens(accessToken: String, refreshToken: String) {
        this.accessToken = accessToken
        this.refreshToken = refreshToken
    }

    override fun clearTokens() {
        accessToken = null
        refreshToken = null
    }

    private fun respond(): AuthResponse {
        error?.let { throw it }
        updateTokens(response.accessToken, response.refreshToken)
        return response
    }
}
