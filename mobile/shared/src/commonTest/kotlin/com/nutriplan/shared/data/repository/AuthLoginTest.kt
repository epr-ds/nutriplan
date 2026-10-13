package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.local.StoredTokens
import com.nutriplan.shared.data.local.TokenStorage
import com.nutriplan.shared.data.model.LoginRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.HttpClientProvider
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AuthLoginTest {

    private class RecordingStorage : TokenStorage {
        var stored: StoredTokens? = null
        override fun load(): StoredTokens? = stored
        override fun save(accessToken: String, refreshToken: String) {
            stored = StoredTokens(accessToken, refreshToken)
        }
        override fun clear() {
            stored = null
        }
    }

    private val json = headersOf(HttpHeaders.ContentType, "application/json")

    @AfterTest
    fun tearDown() = HttpClientProvider.reset()

    private fun respondWith(status: HttpStatusCode, body: String) {
        HttpClientProvider.create(
            MockEngine { respond(content = body, status = status, headers = json) },
            authRepository = null,
        )
    }

    @Test
    fun `successful login stores and persists the returned tokens`() = runTest {
        respondWith(HttpStatusCode.OK, """{"accessToken":"a1","refreshToken":"r1","expiresIn":900}""")
        val storage = RecordingStorage()
        val repo = InMemoryAuthRepository(storage)

        val response = repo.login(LoginRequest("ana@example.com", "secret"))

        assertEquals("a1", response.accessToken)
        assertTrue(repo.isAuthenticated)
        assertEquals("r1", repo.currentRefreshToken)
        assertEquals(StoredTokens("a1", "r1"), storage.stored)
    }

    @Test
    fun `rejected login throws and leaves the user logged out`() = runTest {
        respondWith(HttpStatusCode.Unauthorized, """{"error":"invalid_credentials"}""")
        val storage = RecordingStorage()
        val repo = InMemoryAuthRepository(storage)

        val error = assertFailsWith<ApiException.HttpError> {
            repo.login(LoginRequest("ana@example.com", "wrong"))
        }

        assertEquals(401, error.statusCode)
        assertFalse(repo.isAuthenticated)
        assertEquals(null, storage.stored)
    }

    @Test
    fun `auth error messages never reveal whether an account exists`() {
        assertEquals("Incorrect email or password.", ApiException.HttpError(401, null).toAuthErrorMessage())
        assertEquals("Incorrect email or password.", ApiException.HttpError(400, null).toAuthErrorMessage())
        assertEquals("Incorrect email or password.", ApiException.HttpError(403, null).toAuthErrorMessage())
    }

    @Test
    fun `auth error messages distinguish rate limits, server and network failures`() {
        assertEquals(
            "Too many attempts. Please wait a moment and try again.",
            ApiException.HttpError(429, null).toAuthErrorMessage(),
        )
        assertEquals(
            "The server had a problem. Please try again later.",
            ApiException.HttpError(503, null).toAuthErrorMessage(),
        )
        assertEquals(
            "Can't reach the server. Check your connection and try again.",
            ApiException.NetworkError().toAuthErrorMessage(),
        )
        assertEquals("Something went wrong. Please try again.", IllegalStateException("x").toAuthErrorMessage())
    }
}
