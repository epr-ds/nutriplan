package com.nutriplan.shared.auth

import com.nutriplan.shared.data.network.ApiException

/**
 * A field-level validation failure, shown inline under the offending input.
 *
 * The shared layer emits these stable codes rather than user-facing text so each platform renders
 * its own localized microcopy (IDN-902, es/en).
 */
enum class FieldError {
    NAME_REQUIRED,
    NAME_TOO_SHORT,
    EMAIL_REQUIRED,
    EMAIL_INVALID,
    PASSWORD_REQUIRED,
    PASSWORD_TOO_SHORT,
    CONFIRM_PASSWORD_REQUIRED,
    CONFIRM_PASSWORD_MISMATCH,
}

/**
 * A form-level auth failure: a rejected sign-in/registration or a transport error.
 *
 * Wrong credentials deliberately share one code so the screen does not reveal whether an email
 * address has an account. The platform UI maps these to localized microcopy (IDN-902).
 */
enum class AuthError {
    /** Wrong email/password. Also used for a rejected 400/403 so accounts are not revealed. */
    INVALID_CREDENTIALS,

    /** Rate limited (HTTP 429). */
    TOO_MANY_ATTEMPTS,

    /** The server failed (HTTP 5xx). */
    SERVER_PROBLEM,

    /** Any other HTTP failure, e.g. a rejected registration. */
    LOGIN_FAILED,

    /** The device could not reach the server. */
    NETWORK,

    /** Anything else: offline SDK failures or an unexpected error. */
    UNKNOWN,
}

/** Maps a thrown auth/transport failure to a stable, localizable [AuthError]. */
fun Throwable.toAuthError(): AuthError = when (this) {
    is ApiException.HttpError -> when (statusCode) {
        400, 401, 403 -> AuthError.INVALID_CREDENTIALS
        429 -> AuthError.TOO_MANY_ATTEMPTS
        in 500..599 -> AuthError.SERVER_PROBLEM
        else -> AuthError.LOGIN_FAILED
    }
    is ApiException.NetworkError -> AuthError.NETWORK
    else -> AuthError.UNKNOWN
}
