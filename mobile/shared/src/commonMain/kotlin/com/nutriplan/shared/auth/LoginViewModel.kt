package com.nutriplan.shared.auth

import com.nutriplan.shared.data.repository.toAuthErrorMessage
import com.nutriplan.shared.session.Login
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/**
 * Observable state of the login form.
 *
 * Field-level errors are shown inline under the inputs; [errorMessage] is the form-level message
 * for a rejected sign-in (wrong credentials, network, rate limit). [isSuccess] tells the screen to
 * route to the next destination for the resulting [com.nutriplan.shared.session.SessionState].
 */
data class LoginUiState(
    val email: String = "",
    val password: String = "",
    val emailError: String? = null,
    val passwordError: String? = null,
    val errorMessage: String? = null,
    val isLoading: Boolean = false,
    val isSuccess: Boolean = false,
) {
    /** Whether the form is ready to attempt a sign-in (fields filled and no request in flight). */
    val canSubmit: Boolean get() = !isLoading && email.isNotBlank() && password.isNotBlank()
}

/**
 * Shared login form logic used by the Compose (IDN-501) and SwiftUI (IDN-502) screens.
 *
 * [submit] validates the fields, calls the [Login] use case (which moves the [SessionManager]
 * forward per user state), and maps failures to a user-facing message. It is `suspend` so the UI
 * owns the coroutine scope and cancellation on navigation is handled by Compose/SwiftUI.
 */
class LoginViewModel(
    private val login: Login,
) {

    private val _state = MutableStateFlow(LoginUiState())
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    fun onEmailChange(value: String) {
        _state.update { it.copy(email = value, emailError = null, errorMessage = null) }
    }

    fun onPasswordChange(value: String) {
        _state.update { it.copy(password = value, passwordError = null, errorMessage = null) }
    }

    /** Validates the fields, setting inline errors. Returns true when the form is valid. */
    fun validate(): Boolean {
        val current = _state.value
        val email = current.email.trim()
        val emailError = when {
            email.isEmpty() -> "Enter your email."
            !EMAIL_PATTERN.matches(email) -> "Enter a valid email address."
            else -> null
        }
        val passwordError = if (current.password.isEmpty()) "Enter your password." else null
        _state.update { it.copy(emailError = emailError, passwordError = passwordError) }
        return emailError == null && passwordError == null
    }

    /**
     * Attempts a sign-in. Returns true on success (the caller then routes based on session state);
     * false on validation failure or a rejected request, with [LoginUiState.errorMessage] set.
     * [CancellationException] is rethrown so navigating away cancels cleanly.
     */
    suspend fun submit(): Boolean {
        if (!validate()) return false

        _state.update { it.copy(isLoading = true, errorMessage = null) }
        return try {
            login(email = _state.value.email.trim(), password = _state.value.password)
            _state.update { it.copy(isLoading = false, isSuccess = true, password = "") }
            true
        } catch (e: CancellationException) {
            _state.update { it.copy(isLoading = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(isLoading = false, errorMessage = e.toAuthErrorMessage()) }
            false
        }
    }

    private companion object {
        val EMAIL_PATTERN = Regex("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")
    }
}
