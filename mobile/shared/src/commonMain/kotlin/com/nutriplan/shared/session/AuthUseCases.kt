package com.nutriplan.shared.session

import com.nutriplan.shared.data.model.AuthResponse
import com.nutriplan.shared.data.model.LoginRequest
import com.nutriplan.shared.data.model.OAuthRequest
import com.nutriplan.shared.data.model.RegisterRequest
import com.nutriplan.shared.data.repository.AuthRepository

/**
 * Authenticate an existing user and move the session forward.
 *
 * On success the returned profile is handed to [SessionManager], which routes the user to either
 * the onboarding flow or the main graph. Failures propagate so the UI can show a message.
 */
class Login(
    private val authRepository: AuthRepository,
    private val sessionManager: SessionManager,
) {
    suspend operator fun invoke(email: String, password: String): AuthResponse {
        val response = authRepository.login(LoginRequest(email = email, password = password))
        sessionManager.onAuthenticated(response.user)
        return response
    }
}

/** Create an account; a brand-new user always lands in onboarding. */
class Register(
    private val authRepository: AuthRepository,
    private val sessionManager: SessionManager,
) {
    suspend operator fun invoke(email: String, password: String, name: String): AuthResponse {
        val response = authRepository.register(
            RegisterRequest(email = email, password = password, name = name),
        )
        sessionManager.onAuthenticated(response.user)
        return response
    }
}

/** Exchange an OAuth identity token (Apple/Google) for a NutriPlan session. */
class OAuthLogin(
    private val authRepository: AuthRepository,
    private val sessionManager: SessionManager,
) {
    suspend operator fun invoke(provider: String, idToken: String, nonce: String? = null): AuthResponse {
        val response = authRepository.oauthLogin(
            provider = provider,
            request = OAuthRequest(idToken = idToken, nonce = nonce),
        )
        sessionManager.onAuthenticated(response.user)
        return response
    }
}

/**
 * End the session.
 *
 * Revokes the refresh token server-side first (`POST /auth/logout`) so a stolen token can no
 * longer be rotated, then clears the stored tokens and flips the observed state to
 * [SessionState.SignedOut]. Revocation is best-effort: if the call fails (e.g. the device is
 * offline) the local session is still cleared — logging out must never be blocked.
 */
class Logout(
    private val authRepository: AuthRepository,
    private val sessionManager: SessionManager,
) {
    suspend operator fun invoke() {
        authRepository.currentRefreshToken?.let { refreshToken ->
            runCatching { authRepository.revokeSession(refreshToken) }
        }
        authRepository.clearTokens()
        sessionManager.onSignedOut()
    }
}
