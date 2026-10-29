package com.nutriplan.shared.auth

import com.nutriplan.shared.session.Register
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/**
 * Observable state of the registration form.
 *
 * Per-field errors are shown inline under the inputs; [error] carries a form-level failure code
 * (e.g. the email is already registered). [isSuccess] tells the screen to route into onboarding.
 * The UI turns the codes into localized microcopy.
 */
data class RegisterUiState(
    val name: String = "",
    val email: String = "",
    val password: String = "",
    val confirmPassword: String = "",
    val nameError: FieldError? = null,
    val emailError: FieldError? = null,
    val passwordError: FieldError? = null,
    val confirmPasswordError: FieldError? = null,
    val error: AuthError? = null,
    val isLoading: Boolean = false,
    val isSuccess: Boolean = false,
) {
    /** Whether every field is filled and no request is in flight. */
    val canSubmit: Boolean
        get() = !isLoading &&
            name.isNotBlank() &&
            email.isNotBlank() &&
            password.isNotBlank() &&
            confirmPassword.isNotBlank()
}

/**
 * Shared registration form logic used by the Compose (IDN-503) and SwiftUI (IDN-504) screens.
 *
 * Rules mirror the identity service contract: a name of at least 2 characters, a valid email, and a
 * password of at least 8 characters confirmed twice. [submit] calls the [Register] use case, which
 * always moves a brand-new user into the onboarding flow.
 */
class RegisterViewModel(
    private val register: Register,
) {

    private val _state = MutableStateFlow(RegisterUiState())
    val state: StateFlow<RegisterUiState> = _state.asStateFlow()

    /** The current UI state, for callers that read rather than observe it (e.g. the SwiftUI bridge). */
    fun currentState(): RegisterUiState = _state.value

    fun onNameChange(value: String) {
        _state.update { it.copy(name = value, nameError = null, error = null) }
    }

    fun onEmailChange(value: String) {
        _state.update { it.copy(email = value, emailError = null, error = null) }
    }

    fun onPasswordChange(value: String) {
        _state.update { it.copy(password = value, passwordError = null, confirmPasswordError = null, error = null) }
    }

    fun onConfirmPasswordChange(value: String) {
        _state.update { it.copy(confirmPassword = value, confirmPasswordError = null, error = null) }
    }

    /** Validates the fields, setting inline errors. Returns true when the form is valid. */
    fun validate(): Boolean {
        val current = _state.value
        val name = current.name.trim()
        val email = current.email.trim()

        val nameError = when {
            name.isEmpty() -> FieldError.NAME_REQUIRED
            name.length < MIN_NAME_LENGTH -> FieldError.NAME_TOO_SHORT
            else -> null
        }
        val emailError = when {
            email.isEmpty() -> FieldError.EMAIL_REQUIRED
            !EMAIL_PATTERN.matches(email) -> FieldError.EMAIL_INVALID
            else -> null
        }
        val passwordError = when {
            current.password.isEmpty() -> FieldError.PASSWORD_REQUIRED
            current.password.length < MIN_PASSWORD_LENGTH -> FieldError.PASSWORD_TOO_SHORT
            else -> null
        }
        val confirmPasswordError = when {
            current.confirmPassword.isEmpty() -> FieldError.CONFIRM_PASSWORD_REQUIRED
            current.confirmPassword != current.password -> FieldError.CONFIRM_PASSWORD_MISMATCH
            else -> null
        }

        _state.update {
            it.copy(
                nameError = nameError,
                emailError = emailError,
                passwordError = passwordError,
                confirmPasswordError = confirmPasswordError,
            )
        }
        return nameError == null && emailError == null && passwordError == null && confirmPasswordError == null
    }

    /**
     * Attempts to create the account. Returns true on success; false on validation failure or a
     * rejected request, with [RegisterUiState.error] set. [CancellationException] is
     * rethrown so navigating away cancels cleanly.
     */
    suspend fun submit(): Boolean {
        if (!validate()) return false

        _state.update { it.copy(isLoading = true, error = null) }
        return try {
            register(
                email = _state.value.email.trim(),
                password = _state.value.password,
                name = _state.value.name.trim(),
            )
            _state.update {
                it.copy(isLoading = false, isSuccess = true, password = "", confirmPassword = "")
            }
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
        const val MIN_NAME_LENGTH = 2
        const val MIN_PASSWORD_LENGTH = 8
        val EMAIL_PATTERN = Regex("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")
    }
}
