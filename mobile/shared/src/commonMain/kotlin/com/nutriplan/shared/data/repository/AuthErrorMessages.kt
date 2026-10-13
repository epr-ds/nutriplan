package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.network.ApiException

/**
 * A message safe to show to the user for a failed login or registration.
 *
 * Wrong credentials deliberately share one message so the screen does not reveal whether an
 * email address has an account.
 */
fun Throwable.toAuthErrorMessage(): String = when (this) {
    is ApiException.HttpError -> when (statusCode) {
        400, 401, 403 -> "Incorrect email or password."
        429 -> "Too many attempts. Please wait a moment and try again."
        in 500..599 -> "The server had a problem. Please try again later."
        else -> "Login failed. Please try again."
    }
    is ApiException.NetworkError -> "Can't reach the server. Check your connection and try again."
    else -> "Something went wrong. Please try again."
}
