package com.nutriplan.shared.session

import com.nutriplan.shared.data.network.ApiException
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

class AuthUseCasesTest {

    @Test
    fun `login stores the session and routes a returning user to the main graph`() = runTest {
        val repository = FakeAuthRepository(authResponse(onboardingComplete = true))
        val manager = DefaultSessionManager(repository, backgroundScope)

        val response = Login(repository, manager)("ana@example.com", "correct-horse")

        assertEquals("access-1", response.accessToken)
        assertEquals("access-1", repository.currentAccessToken)
        assertEquals("refresh-1", repository.currentRefreshToken)
        assertIs<SessionState.SignedIn>(manager.state.value)
    }

    @Test
    fun `register routes a brand-new user to onboarding`() = runTest {
        val repository = FakeAuthRepository(authResponse(onboardingComplete = false))
        val manager = DefaultSessionManager(repository, backgroundScope)

        Register(repository, manager)("ana@example.com", "correct-horse", "Ana")

        assertEquals(SessionState.Onboarding, manager.state.value)
        assertTrue(repository.isAuthenticated)
    }

    @Test
    fun `oauth login forwards the provider and identity token`() = runTest {
        val repository = FakeAuthRepository(authResponse(onboardingComplete = true))
        val manager = DefaultSessionManager(repository, backgroundScope)

        OAuthLogin(repository, manager)(provider = "google", idToken = "id-token", nonce = "n1")

        assertEquals("google", repository.lastOAuthProvider)
        assertEquals("id-token", repository.lastOAuthRequest?.idToken)
        assertEquals("n1", repository.lastOAuthRequest?.nonce)
        assertIs<SessionState.SignedIn>(manager.state.value)
    }

    @Test
    fun `a rejected login propagates and leaves the session signed out`() = runTest {
        val repository = FakeAuthRepository(error = ApiException.HttpError(statusCode = 401, body = null))
        val manager = DefaultSessionManager(repository, backgroundScope)

        assertFailsWith<ApiException.HttpError> { Login(repository, manager)("ana@example.com", "wrong") }

        assertEquals(SessionState.SignedOut, manager.state.value)
        assertNull(repository.currentAccessToken)
    }

    @Test
    fun `logout clears the session`() = runTest {
        val repository = FakeAuthRepository()
        val manager = DefaultSessionManager(repository, backgroundScope)
        Login(repository, manager)("ana@example.com", "correct-horse")

        Logout(repository, manager)()

        assertEquals(SessionState.SignedOut, manager.state.value)
        assertNull(repository.currentAccessToken)
        assertNull(repository.currentRefreshToken)
    }
}
