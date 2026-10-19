package com.nutriplan.shared.data.network

/**
 * What kind of problem a failed API call was, independent of how it was thrown.
 *
 * The data layer throws [ApiException] in two shapes: [ApiException.HttpError] carries the HTTP
 * status, while the repositories' `ApiException.create(...)` helper (despite returning a
 * `NetworkError`) is used for 401/403/404 and carries a [ApiException.Code]. Callers must not
 * branch on the class alone: a 401 is not an offline device. This is the one place that reads both.
 */
enum class ApiFailure {
    /** The device could not reach the server (no connection, DNS failure, timeout). */
    OFFLINE,

    /** The server rejected the session (HTTP 401): the user has to sign in again. */
    SESSION_EXPIRED,

    /** HTTP 403. */
    FORBIDDEN,

    /** HTTP 404: the resource does not exist, or is not visible to the caller. */
    NOT_FOUND,

    /** HTTP 409: the request conflicts with the resource's current state. */
    CONFLICT,

    /** HTTP 400 or 422: the server refused the request's content. */
    REJECTED,

    /** HTTP 5xx. */
    SERVER,

    /** Anything else, including a response that could not be read. */
    UNKNOWN,
}

/** Classifies any failure thrown by a repository call; see [ApiFailure]. */
fun Throwable.toApiFailure(): ApiFailure = when (this) {
    is ApiException.HttpError -> when (statusCode) {
        401 -> ApiFailure.SESSION_EXPIRED
        403 -> ApiFailure.FORBIDDEN
        404 -> ApiFailure.NOT_FOUND
        409 -> ApiFailure.CONFLICT
        400, 422 -> ApiFailure.REJECTED
        in 500..599 -> ApiFailure.SERVER
        else -> ApiFailure.UNKNOWN
    }
    is ApiException -> when (code) {
        ApiException.Code.NETWORK_ERROR -> ApiFailure.OFFLINE
        ApiException.Code.UNAUTHORIZED -> ApiFailure.SESSION_EXPIRED
        ApiException.Code.FORBIDDEN -> ApiFailure.FORBIDDEN
        ApiException.Code.NOT_FOUND -> ApiFailure.NOT_FOUND
        ApiException.Code.CONFLICT -> ApiFailure.CONFLICT
        ApiException.Code.SERVER_ERROR -> ApiFailure.SERVER
        else -> ApiFailure.UNKNOWN
    }
    else -> ApiFailure.UNKNOWN
}
