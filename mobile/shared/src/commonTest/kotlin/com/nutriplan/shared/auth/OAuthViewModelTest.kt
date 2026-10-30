package com.nutriplan.shared.auth

import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.session.DefaultSessionManager
import com.nutriplan.shared.session.FakeAuthRepository
import com.nutriplan.shared.session.OAuthLogin
import com.nutriplan.shared.session.SessionState
import com.nutriplan.shared.session.authResponse
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

class OAuthViewModelTest {

    private class Fixture(
        val model: OAuthViewModel,
        val repository: FakeAuthRepository,
        val provider: FakeOAuthTokenProvider,
        val session: DefaultSessionManager,
    )

    private fun fixture(
        scope: CoroutineScope,
        token: OAuthToken? = OAuthToken(idToken = "id-token-1"),
        providerError: Throwable? = null,
        supported: Set<OAuthProvider> = setOf(OAuthProvider.GOOGLE, OAuthProvider.APPLE),
    ): Fixture {
        val repository = FakeAuthRepository(response = authResponse(onboardingComplete = false))
        val session = DefaultSessionManager(FakeAuthRepository(), scope)
        val provider = FakeOAuthTokenProvider(
            supportedProviders = supported,
            token = token,
            error = providerError,
        )
        return Fixture(OAuthViewModel(OAuthLogin(repository, session), provider), repository, provider, session)
    }

    @Test
    fun `the oauth flow exposes its current state`() = runTest {
        val fx = fixture(backgroundScope)

        val state = fx.model.currentState()
        assertFalse(state.isLoading)
        assertNull(state.error)
        assertFalse(state.isSuccess)
    }

    @Test
    fun `the current state is the latest one`() = runTest {
        val fx = fixture(backgroundScope)

        assertTrue(fx.model.signIn(OAuthProvider.GOOGLE))

        val state = fx.model.currentState()
        assertTrue(state.isSuccess)
        assertFalse(state.isLoading)
        assertNull(state.error)
    }

    @Test
    fun `exposes the providers the platform supports`() = runTest {
        val fx = fixture(backgroundScope, supported = setOf(OAuthProvider.GOOGLE))

        assertEquals(setOf(OAuthProvider.GOOGLE), fx.model.supportedProviders)
    }

    @Test
    fun `a successful google sign-in exchanges the token and lands in onboarding`() = runTest {
        val fx = fixture(backgroundScope)

        assertTrue(fx.model.signIn(OAuthProvider.GOOGLE))

        val state = fx.model.state.value
        assertTrue(state.isSuccess)
        assertFalse(state.isLoading)
        assertNull(state.activeProvider)
        assertNull(state.error)
        assertEquals("google", fx.repository.lastOAuthProvider)
        assertEquals("id-token-1", fx.repository.lastOAuthRequest?.idToken)
        assertIs<SessionState.Onboarding>(fx.session.state.value)
    }

    @Test
    fun `the provider slug and nonce are forwarded for apple`() = runTest {
        val fx = fixture(backgroundScope, token = OAuthToken(idToken = "apple-token", nonce = "n-1"))

        assertTrue(fx.model.signIn(OAuthProvider.APPLE))

        assertEquals("apple", fx.repository.lastOAuthProvider)
        assertEquals("apple-token", fx.repository.lastOAuthRequest?.idToken)
        assertEquals("n-1", fx.repository.lastOAuthRequest?.nonce)
    }

    @Test
    fun `a cancelled consent sheet is not an error`() = runTest {
        val fx = fixture(backgroundScope, token = null)

        assertFalse(fx.model.signIn(OAuthProvider.GOOGLE))

        val state = fx.model.state.value
        assertFalse(state.isSuccess)
        assertFalse(state.isLoading)
        assertNull(state.error)
        assertNull(fx.repository.lastOAuthProvider)
    }

    @Test
    fun `a rejected exchange surfaces a message`() = runTest {
        val repository = FakeAuthRepository(
            response = authResponse(onboardingComplete = false),
            error = ApiException.HttpError(401, null),
        )
        val session = DefaultSessionManager(FakeAuthRepository(), backgroundScope)
        val model = OAuthViewModel(OAuthLogin(repository, session), FakeOAuthTokenProvider())

        assertFalse(model.signIn(OAuthProvider.GOOGLE))

        val state = model.state.value
        assertEquals(AuthError.INVALID_CREDENTIALS, state.error)
        assertFalse(state.isLoading)
        assertFalse(state.isSuccess)
    }

    @Test
    fun `a failing provider surfaces a message`() = runTest {
        val fx = fixture(backgroundScope, providerError = IllegalStateException("no play services"))

        assertFalse(fx.model.signIn(OAuthProvider.GOOGLE))

        assertEquals(AuthError.UNKNOWN, fx.model.state.value.error)
    }

    @Test
    fun `sign-in propagates cancellation`() = runTest {
        val fx = fixture(backgroundScope, providerError = CancellationException("cancelled"))

        assertFailsWith<CancellationException> { fx.model.signIn(OAuthProvider.GOOGLE) }

        assertFalse(fx.model.state.value.isLoading)
    }
}

/** In-memory [OAuthTokenProvider] for tests. */
internal class FakeOAuthTokenProvider(
    override val supportedProviders: Set<OAuthProvider> = setOf(OAuthProvider.GOOGLE),
    private val token: OAuthToken? = OAuthToken("id-token-1"),
    private val error: Throwable? = null,
) : OAuthTokenProvider {

    val requested: MutableList<OAuthProvider> = mutableListOf()

    override suspend fun signIn(provider: OAuthProvider): OAuthToken? {
        requested += provider
        error?.let { throw it }
        return token
    }
}
