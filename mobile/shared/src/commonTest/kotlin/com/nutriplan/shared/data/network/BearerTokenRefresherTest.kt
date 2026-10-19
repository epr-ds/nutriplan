package com.nutriplan.shared.data.network

import com.nutriplan.shared.data.model.AuthResponse
import com.nutriplan.shared.data.model.LoginRequest
import com.nutriplan.shared.data.model.OAuthRequest
import com.nutriplan.shared.data.model.RegisterRequest
import com.nutriplan.shared.data.model.UserProfile
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.session.SessionEvents
import io.ktor.utils.io.errors.IOException
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class BearerTokenRefresherTest {

    private class FakeAuthRepository(
        private var access: String? = "access-0",
        private var refresh: String? = "refresh-0",
    ) : AuthRepository {
        var refreshCalls = 0
        var cleared = false
        var failRefresh = false
        var failWith: Throwable? = null

        override val currentAccessToken: String? get() = access
        override val currentRefreshToken: String? get() = refresh
        override val isAuthenticated: Boolean get() = access != null

        override suspend fun register(request: RegisterRequest): AuthResponse = error("not used")

        override suspend fun login(request: LoginRequest): AuthResponse = error("not used")

        override suspend fun oauthLogin(provider: String, request: OAuthRequest): AuthResponse =
            error("not used")

        override suspend fun refreshToken(refreshToken: String): AuthResponse {
            refreshCalls++
            delay(10)
            failWith?.let { throw it }
            if (failRefresh) throw ApiException.HttpError(statusCode = 401, body = null)
            return AuthResponse(
                accessToken = "access-$refreshCalls",
                refreshToken = "refresh-$refreshCalls",
                expiresIn = 900,
                user = UserProfile(id = "u1", email = "ana@example.com", name = "Ana"),
            )
        }

        override fun updateTokens(accessToken: String, refreshToken: String) {
            access = accessToken
            refresh = refreshToken
        }

        override suspend fun revokeSession(refreshToken: String) = Unit

        override fun clearTokens() {
            access = null
            refresh = null
            cleared = true
        }
    }

    @Test
    fun `concurrent refreshes perform exactly one network call and share the result`() = runTest {
        val repository = FakeAuthRepository()
        val refresher = BearerTokenRefresher(repository)

        val tokens = List(5) { async { refresher.refresh("refresh-0") } }.awaitAll()

        assertEquals(1, repository.refreshCalls)
        assertTrue(tokens.all { it.accessToken == "access-1" })
        assertTrue(tokens.all { it.refreshToken == "refresh-1" })
    }

    @Test
    fun `a refresh of an already-rotated token reuses the current tokens`() = runTest {
        val repository = FakeAuthRepository()
        val refresher = BearerTokenRefresher(repository)

        refresher.refresh("refresh-0")
        val tokens = refresher.refresh("refresh-0")

        assertEquals(1, repository.refreshCalls)
        assertEquals("access-1", tokens.accessToken)
    }

    @Test
    fun `a failed refresh clears the session and emits a signed-out event`() = runTest {
        val repository = FakeAuthRepository().apply { failRefresh = true }
        val refresher = BearerTokenRefresher(repository)

        val collector = launch { SessionEvents.signedOut.first() }
        advanceUntilIdle()

        assertFailsWith<ApiException.HttpError> { refresher.refresh("refresh-0") }
        advanceUntilIdle()

        assertEquals(1, repository.refreshCalls)
        assertTrue(repository.cleared)
        assertTrue(collector.isCompleted)
    }

    @Test
    fun `a refresh that fails because the connection dropped keeps the session`() = runTest {
        val repository = FakeAuthRepository().apply { failWith = ApiException.NetworkError() }
        val refresher = BearerTokenRefresher(repository)

        assertFailsWith<ApiException.NetworkError> { refresher.refresh("refresh-0") }

        assertFalse(repository.cleared, "the user must not be signed out because the network failed")
        assertEquals("refresh-0", repository.currentRefreshToken)
    }

    @Test
    fun `a raw transport failure during refresh also keeps the session`() = runTest {
        val repository = FakeAuthRepository().apply { failWith = IOException("connection reset") }
        val refresher = BearerTokenRefresher(repository)

        assertFailsWith<IOException> { refresher.refresh("refresh-0") }

        assertFalse(repository.cleared)
        assertEquals("refresh-0", repository.currentRefreshToken)
    }

    @Test
    fun `a refresh the server rejects still ends the session`() = runTest {
        val repository = FakeAuthRepository().apply { failWith = ApiException.HttpError(statusCode = 400, body = null) }
        val refresher = BearerTokenRefresher(repository)

        assertFailsWith<ApiException.HttpError> { refresher.refresh("refresh-0") }

        assertTrue(repository.cleared)
    }
}
