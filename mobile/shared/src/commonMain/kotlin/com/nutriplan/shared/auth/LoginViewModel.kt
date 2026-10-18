package com.nutriplan.shared.auth

import com.nutriplan.shared.session.Login
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/**
 * Observable state of the login form.
 *
 * Field-level errors are shown inline under the inputs; [error] is the form-level code for a
 * rejected sign-in (wrong credentials, network, rate limit). [isSuccess] tells the screen to route
 * to the next destination for the resulting [com.nutriplan.shared.session.SessionState]. The UI
 * turns the codes into localized microcopy.
 */
data class LoginUiState(
    val email: String = "",
    val password: String = "",
    val emailError: FieldError? = null,
    val passwordError: FieldError? = null,
    val error: AuthError? = null,
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
        _state.update { it.copy(email = value, emailError = null, error = null) }
    }

    fun onPasswordChange(value: String) {
        _state.update { it.copy(password = value, passwordError = null, error = null) }
    }

    /** Validates the fields, setting inline errors. Returns true when the form is valid. */
    fun validate(): Boolean {
        val current = _state.value
        val email = current.email.trim()
        val emailError = when {
            email.isEmpty() -> FieldError.EMAIL_REQUIRED
            !EMAIL_PATTERN.matches(email) -> FieldError.EMAIL_INVALID
            else -> null
        }
        val passwordError = if (current.password.isEmpty()) FieldError.PASSWORD_REQUIRED else null
        _state.update { it.copy(emailError = emailError, passwordError = passwordError) }
        return emailError == null && passwordError == null
    }

    /**
     * Attempts a sign-in. Returns true on success (the caller then routes based on session state);
     * false on validation failure or a rejected request, with [LoginUiState.error] set.
     * [CancellationException] is rethrown so navigating away cancels cleanly.
     */
    suspend fun submit(): Boolean {
        if (!validate()) return false

        _state.update { it.copy(isLoading = true, error = null) }
        return try {
            login(email = _state.value.email.trim(), password = _state.value.password)
            _state.update { it.copy(isLoading = false, isSuccess = true, password = "") }
            true
        } catch (e: CancellationException) {
            _state.update { it.copy(isLoading = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(isLoading = false, error = e.toAuthError()) }
            false
        }
    }

    private companion object {
        val EMAIL_PATTERN = Regex("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")
    }
}
