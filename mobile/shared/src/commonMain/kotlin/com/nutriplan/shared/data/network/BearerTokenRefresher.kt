package com.nutriplan.shared.data.network

import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.session.SessionEvents
import io.ktor.client.plugins.auth.providers.BearerTokens
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Single-flight bearer-token refresh for the Ktor `Auth` plugin.
 *
 * When several requests are in flight and all get a 401, each one would otherwise call
 * `POST /auth/refresh` — and because refresh tokens rotate (IDN-105), the later calls would
 * present a token that the first call already invalidated, failing the session. The mutex
 * serialises refreshes and the "already rotated" check lets the losers reuse the winner's
 * tokens, so a burst of concurrent 401s performs **exactly one** network refresh.
 *
 * A failed refresh is terminal: the tokens are cleared and a global signed-out event is emitted
 * (see [SessionEvents]) so navigation can send the user back to login.
 */
class BearerTokenRefresher(private val authRepository: AuthRepository) {

    private val mutex = Mutex()

    /**
     * Refresh the session that was using [staleRefreshToken] and return the new tokens.
     *
     * @throws Exception when the refresh is rejected; the session is cleared and a signed-out
     *   event is emitted before the original exception propagates.
     */
    suspend fun refresh(staleRefreshToken: String): BearerTokens = mutex.withLock {
        val currentRefreshToken = authRepository.currentRefreshToken
        if (currentRefreshToken != null && currentRefreshToken != staleRefreshToken) {
            // Another request already refreshed while we waited on the lock; reuse its tokens.
            return@withLock BearerTokens(authRepository.currentAccessToken.orEmpty(), currentRefreshToken)
        }

        val response = try {
            authRepository.refreshToken(staleRefreshToken)
        } catch (error: Exception) {
            authRepository.clearTokens()
            SessionEvents.emitSignedOut()
            throw error
        }
        authRepository.updateTokens(response.accessToken, response.refreshToken)
        BearerTokens(response.accessToken, response.refreshToken)
    }
}
