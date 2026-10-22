package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.toApiFailure

/** Why an order operation did not give a result. Locale-neutral: each platform maps these to its own copy. */
enum class OrderError {
    /** The device could not reach the server. */
    NETWORK,

    /** The server failed (HTTP 5xx), or a provider behind it could not be reached. */
    SERVER_PROBLEM,

    /** The server rejected the session (HTTP 401): the user has to sign in again. */
    SESSION_EXPIRED,

    /** The order (or the meal plan it is for) does not exist, or is not the caller's. */
    NOT_FOUND,

    /** The order cannot do that in its current state (HTTP 409), e.g. cancelling a delivered order. */
    CONFLICT,

    /** The card was declined (HTTP 402); no order was created. */
    PAYMENT_DECLINED,

    /** The request was refused (HTTP 400/422), e.g. a refund larger than the total. */
    REJECTED,

    /** Anything else. */
    UNKNOWN,
}

/** The typed result of an order operation: a value, or why there is none. */
sealed interface OrderResult<out T> {
    data class Success<out T>(val value: T) : OrderResult<T>
    data class Failure(val error: OrderError) : OrderResult<Nothing>
}

/**
 * What a cache-first read shows: the orders (or order) and whether they are the server's answer.
 *
 * A read emits the device's copy first ([fresh] false) and then the server's ([fresh] true). When the
 * server cannot be reached the copy stays on screen with [refreshError] saying why it is not fresh.
 */
data class Fetched<out T>(
    val value: T,
    val fresh: Boolean,
    val refreshError: OrderError? = null,
)

/** Maps a thrown repository failure to a stable, localizable [OrderError]. */
fun Throwable.toOrderError(): OrderError {
    if (this is ApiException.HttpError && statusCode == HTTP_PAYMENT_REQUIRED) return OrderError.PAYMENT_DECLINED
    return when (toApiFailure()) {
        ApiFailure.OFFLINE -> OrderError.NETWORK
        ApiFailure.SERVER -> OrderError.SERVER_PROBLEM
        ApiFailure.SESSION_EXPIRED -> OrderError.SESSION_EXPIRED
        ApiFailure.NOT_FOUND -> OrderError.NOT_FOUND
        ApiFailure.CONFLICT -> OrderError.CONFLICT
        ApiFailure.REJECTED -> OrderError.REJECTED
        else -> OrderError.UNKNOWN
    }
}

private const val HTTP_PAYMENT_REQUIRED = 402
