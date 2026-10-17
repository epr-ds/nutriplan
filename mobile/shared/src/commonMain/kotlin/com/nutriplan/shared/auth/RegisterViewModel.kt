package com.nutriplan.shared.auth

import com.nutriplan.shared.data.repository.toAuthErrorMessage
import com.nutriplan.shared.session.Register
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/**
 * Observable state of the registration form.
 *
 * Per-field errors are shown inline under the inputs; [errorMessage] carries a form-level failure
 * (e.g. the email is already registered). [isSuccess] tells the screen to route into onboarding.
 */
data class RegisterUiState(
    val name: String = "",
    val email: String = "",
    val password: String = "",
    val confirmPassword: String = "",
    val nameError: String? = null,
    val emailError: String? = null,
    val passwordError: String? = null,
    val confirmPasswordError: String? = null,
    val errorMessage: String? = null,
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

    fun onNameChange(value: String) {
        _state.update { it.copy(name = value, nameError = null, errorMessage = null) }
    }

    fun onEmailChange(value: String) {
        _state.update { it.copy(email = value, emailError = null, errorMessage = null) }
    }

    fun onPasswordChange(value: String) {
        _state.update { it.copy(password = value, passwordError = null, confirmPasswordError = null, errorMessage = null) }
    }

    fun onConfirmPasswordChange(value: String) {
        _state.update { it.copy(confirmPassword = value, confirmPasswordError = null, errorMessage = null) }
    }

    /** Validates the fields, setting inline errors. Returns true when the form is valid. */
    fun validate(): Boolean {
        val current = _state.value
        val name = current.name.trim()
        val email = current.email.trim()

        val nameError = when {
            name.isEmpty() -> "Enter your name."
            name.length < MIN_NAME_LENGTH -> "Use at least $MIN_NAME_LENGTH characters."
            else -> null
        }
        val emailError = when {
            email.isEmpty() -> "Enter your email."
            !EMAIL_PATTERN.matches(email) -> "Enter a valid email address."
            else -> null
        }
        val passwordError = when {
            current.password.isEmpty() -> "Enter a password."
            current.password.length < MIN_PASSWORD_LENGTH -> "Use at least $MIN_PASSWORD_LENGTH characters."
            else -> null
        }
        val confirmPasswordError = when {
            current.confirmPassword.isEmpty() -> "Re-enter your password."
            current.confirmPassword != current.password -> "Passwords don't match."
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
     * rejected request, with [RegisterUiState.errorMessage] set. [CancellationException] is
     * rethrown so navigating away cancels cleanly.
     */
    suspend fun submit(): Boolean {
        if (!validate()) return false

        _state.update { it.copy(isLoading = true, errorMessage = null) }
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
            _state.update { it.copy(isLoading = false, errorMessage = e.toAuthErrorMessage()) }
            false
        }
    }

    private companion object {
        const val MIN_NAME_LENGTH = 2
        const val MIN_PASSWORD_LENGTH = 8
        val EMAIL_PATTERN = Regex("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")
    }
}
