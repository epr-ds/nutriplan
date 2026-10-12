package com.nutriplan.shared.data.network

/**
 * Exception thrown by API calls to represent various failure modes.
 */
sealed class ApiException(
    open val body: String?,
    message: String,
    val code: Code,
) : RuntimeException(message) {
    enum class Code {
        NETWORK_ERROR,
        HTTP_ERROR,
        UNAUTHORIZED,
        FORBIDDEN,
        NOT_FOUND,
        CONFLICT,
        SERVER_ERROR,
        SERIALIZATION_ERROR,
        UNKNOWN,
    }

    companion object {
        fun create(message: String, code: Code): NetworkError =
            NetworkError(errorCause = null, message = message, code = code)
    }

    data class HttpError(
        val statusCode: Int,
        override val body: String?,
    ) : ApiException(
        body = body,
        message = "HTTP $statusCode: ${body ?: "Unknown error"}",
        code = when (statusCode) {
            400 -> Code.CONFLICT
            401 -> Code.UNAUTHORIZED
            403 -> Code.FORBIDDEN
            404 -> Code.NOT_FOUND
            500 -> Code.SERVER_ERROR
            else -> Code.HTTP_ERROR
        },
    )

    data class NetworkError(
        val errorCause: Throwable? = null,
        val message: String = "Network error",
        val code: Code = Code.NETWORK_ERROR,
    ) : ApiException(
        body = null,
        message = message,
        code = code,
    ) {
        override val cause: Throwable? = errorCause
    }

    data class SerializationError(
        val errorCause: Throwable? = null,
        val message: String = "Serialization error",
        val code: Code = Code.SERIALIZATION_ERROR,
    ) : ApiException(
        body = null,
        message = message,
        code = code,
    ) {
        override val cause: Throwable? = errorCause
    }

    data class Unknown(
        override val body: String? = null,
    ) : ApiException(
        body = body,
        message = "Unknown error",
        code = Code.UNKNOWN,
    )
}
