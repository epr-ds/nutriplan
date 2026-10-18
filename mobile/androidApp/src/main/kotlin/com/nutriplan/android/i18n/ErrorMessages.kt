package com.nutriplan.android.i18n

import androidx.annotation.StringRes
import com.nutriplan.android.R
import com.nutriplan.shared.auth.AuthError
import com.nutriplan.shared.auth.FieldError
import com.nutriplan.shared.onboarding.OnboardingError

/**
 * IDN-902: maps the shared layer's stable error codes to localized Android string resources.
 *
 * The shared view-models emit locale-neutral codes; the platform owns the es/en microcopy.
 */
@StringRes
fun FieldError.messageRes(): Int = when (this) {
    FieldError.NAME_REQUIRED -> R.string.error_field_name_required
    FieldError.NAME_TOO_SHORT -> R.string.error_field_name_too_short
    FieldError.EMAIL_REQUIRED -> R.string.error_field_email_required
    FieldError.EMAIL_INVALID -> R.string.error_field_email_invalid
    FieldError.PASSWORD_REQUIRED -> R.string.error_field_password_required
    FieldError.PASSWORD_TOO_SHORT -> R.string.error_field_password_too_short
    FieldError.CONFIRM_PASSWORD_REQUIRED -> R.string.error_field_confirm_password_required
    FieldError.CONFIRM_PASSWORD_MISMATCH -> R.string.error_field_confirm_password_mismatch
}

@StringRes
fun AuthError.messageRes(): Int = when (this) {
    AuthError.INVALID_CREDENTIALS -> R.string.error_auth_invalid_credentials
    AuthError.TOO_MANY_ATTEMPTS -> R.string.error_auth_too_many_attempts
    AuthError.SERVER_PROBLEM -> R.string.error_auth_server_problem
    AuthError.LOGIN_FAILED -> R.string.error_auth_login_failed
    AuthError.NETWORK -> R.string.error_auth_network
    AuthError.UNKNOWN -> R.string.error_auth_unknown
}

@StringRes
fun OnboardingError.messageRes(): Int = when (this) {
    OnboardingError.SAVE_FAILED -> R.string.error_onboarding_save_failed
}
