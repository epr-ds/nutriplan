package com.nutriplan.shared.auth

import com.nutriplan.shared.data.repository.toAuthErrorMessage
import com.nutriplan.shared.session.OAuthLogin
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/**
 * Observable state of the OAuth sign-in flow.
 *
 * [activeProvider] is the provider currently showing native consent (so the UI can show a spinner
 * on the tapped button); [errorMessage] carries a form-level failure. [isSuccess] tells the screen
 * to route to the next destination for the resulting session state.
 */
data class OAuthUiState(
    val isLoading: Boolean = false,
    val activeProvider: OAuthProvider? = null,
    val errorMessage: String? = null,
    val isSuccess: Boolean = false,
) {
    /** Whether another sign-in can be started. */
    val canSubmit: Boolean get() = !isLoading
}

/**
 * Shared OAuth flow logic used by the Compose (IDN-505) and SwiftUI (IDN-506) screens.
 *
 * [signIn] runs native consent through the platform [OAuthTokenProvider], then exchanges the
 * resulting id-token with the backend via [OAuthLogin] (which moves the [SessionManager] forward).
 * A dismissed consent sheet returns `false` with no error; other failures map to a user-facing
 * message. It is `suspend` so the UI owns the coroutine scope.
 */
class OAuthViewModel(
    private val oauthLogin: OAuthLogin,
    private val tokenProvider: OAuthTokenProvider,
) {

    /** Providers the current platform can present; drives which buttons the UI shows. */
    val supportedProviders: Set<OAuthProvider> get() = tokenProvider.supportedProviders

    private val _state = MutableStateFlow(OAuthUiState())
    val state: StateFlow<OAuthUiState> = _state.asStateFlow()

    /**
     * Attempts a sign-in with [provider]. Returns true on success; false if the user cancelled or
     * the request was rejected (with [OAuthUiState.errorMessage] set only for the latter).
     * [CancellationException] is rethrown so navigating away cancels cleanly.
     */
    suspend fun signIn(provider: OAuthProvider): Boolean {
        if (_state.value.isLoading) return false

        _state.update { it.copy(isLoading = true, activeProvider = provider, errorMessage = null) }
        return try {
            val token = tokenProvider.signIn(provider)
            if (token == null) {
                // User dismissed the consent screen — not an error.
                _state.update { it.copy(isLoading = false, activeProvider = null) }
                false
            } else {
                oauthLogin(provider = provider.slug, idToken = token.idToken, nonce = token.nonce)
                _state.update { it.copy(isLoading = false, activeProvider = null, isSuccess = true) }
                true
            }
        } catch (e: CancellationException) {
            _state.update { it.copy(isLoading = false, activeProvider = null) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update {
                it.copy(isLoading = false, activeProvider = null, errorMessage = e.toAuthErrorMessage())
            }
            false
        }
    }
}
