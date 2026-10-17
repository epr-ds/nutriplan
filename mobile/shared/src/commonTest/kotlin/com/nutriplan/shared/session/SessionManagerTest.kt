package com.nutriplan.shared.session

import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull

class SessionManagerTest {

    @Test
    fun `starts signed out when there are no stored tokens`() = runTest {
        val manager = DefaultSessionManager(FakeAuthRepository(), backgroundScope)

        assertEquals(SessionState.SignedOut, manager.state.value)
    }

    @Test
    fun `starts in onboarding when a session was restored`() = runTest {
        val manager = DefaultSessionManager(
            FakeAuthRepository(initialAccessToken = "restored"),
            backgroundScope,
        )

        assertEquals(SessionState.Onboarding, manager.state.value)
    }

    @Test
    fun `a fresh authenticated user is routed to onboarding`() = runTest {
        val manager = DefaultSessionManager(FakeAuthRepository(), backgroundScope)

        manager.onAuthenticated(authResponse(onboardingComplete = false).user)

        assertEquals(SessionState.Onboarding, manager.state.value)
    }

    @Test
    fun `a returning authenticated user is routed to the main graph`() = runTest {
        val manager = DefaultSessionManager(FakeAuthRepository(), backgroundScope)

        manager.onAuthenticated(authResponse(onboardingComplete = true).user)

        val state = assertIs<SessionState.SignedIn>(manager.state.value)
        assertEquals("u1", state.user.id)
    }

    @Test
    fun `finishing onboarding promotes the session to signed in`() = runTest {
        val manager = DefaultSessionManager(FakeAuthRepository(), backgroundScope)
        manager.onAuthenticated(authResponse(onboardingComplete = false).user)

        manager.onOnboardingCompleted(authResponse(onboardingComplete = true).user)

        assertIs<SessionState.SignedIn>(manager.state.value)
    }

    @Test
    fun `signing out clears the stored tokens`() = runTest {
        val repository = FakeAuthRepository()
        val manager = DefaultSessionManager(repository, backgroundScope)
        manager.onAuthenticated(authResponse(onboardingComplete = true).user)

        manager.onSignedOut()

        assertEquals(SessionState.SignedOut, manager.state.value)
        assertNull(repository.currentAccessToken)
        assertNull(repository.currentRefreshToken)
        assertFalse(repository.isAuthenticated)
    }

    @Test
    fun `a global signed-out event ends the session`() = runTest {
        val repository = FakeAuthRepository()
        val manager = DefaultSessionManager(repository, backgroundScope)
        manager.onAuthenticated(authResponse(onboardingComplete = true).user)
        advanceUntilIdle()

        SessionEvents.emitSignedOut()
        advanceUntilIdle()

        assertEquals(SessionState.SignedOut, manager.state.value)
        assertNull(repository.currentAccessToken)
    }
}
