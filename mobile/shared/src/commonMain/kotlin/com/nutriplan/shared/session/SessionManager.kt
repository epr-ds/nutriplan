package com.nutriplan.shared.session

import com.nutriplan.shared.data.model.UserProfile
import com.nutriplan.shared.data.repository.AuthRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch

/**
 * Single source of truth for the current [SessionState].
 *
 * Navigation reads [state] to decide between the auth, onboarding, and main graphs (IDN-507);
 * auth use cases tell the manager what happened. A session that ends anywhere — explicit logout
 * or a rejected token refresh — funnels through [SessionEvents.signedOut], so the manager is the
 * one place that reacts to it.
 */
interface SessionManager {

    /** The current session state; collect it to drive navigation. */
    val state: StateFlow<SessionState>

    /** Called after a successful login/register/oauth with the returned profile. */
    fun onAuthenticated(user: UserProfile)

    /** Called once the user finishes onboarding (dietary preferences saved). */
    fun onOnboardingCompleted(user: UserProfile)

    /** Called when the session ends; clears any stored tokens. */
    fun onSignedOut()
}

/**
 * Default [SessionManager].
 *
 * On construction it derives the state from whatever tokens [authRepository] already holds: a
 * restored session is [SessionState.Onboarding] until a profile tells us otherwise. It then
 * follows [SessionEvents.signedOut] on [scope] so a rejected refresh logs the user out everywhere.
 */
class DefaultSessionManager(
    private val authRepository: AuthRepository,
    scope: CoroutineScope,
) : SessionManager {

    private val _state = MutableStateFlow(initialState())
    override val state: StateFlow<SessionState> = _state.asStateFlow()

    init {
        scope.launch {
            SessionEvents.signedOut.collect { onSignedOut() }
        }
    }

    private fun initialState(): SessionState =
        if (authRepository.isAuthenticated) SessionState.Onboarding else SessionState.SignedOut

    override fun onAuthenticated(user: UserProfile) {
        _state.value = if (user.dietaryPreferences == null) {
            SessionState.Onboarding
        } else {
            SessionState.SignedIn(user)
        }
    }

    override fun onOnboardingCompleted(user: UserProfile) {
        _state.value = SessionState.SignedIn(user)
    }

    override fun onSignedOut() {
        authRepository.clearTokens()
        _state.value = SessionState.SignedOut
    }
}
