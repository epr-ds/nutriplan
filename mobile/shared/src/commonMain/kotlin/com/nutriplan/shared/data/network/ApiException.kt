package com.nutriplan.shared.data.network

/**
 * Exception thrown by API calls to represent various failure modes.
 */
sealed class ApiException(
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

    data class HttpError(
        val statusCode: Int,
        override val body: String?,
    ) : ApiException(
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
        override val cause: Throwable?,
    ) : ApiException(
        message = cause?.message ?: "Network error",
        code = Code.NETWORK_ERROR,
    )

    data class SerializationError(
        override val cause: Throwable?,
    ) : ApiException(
        message = cause?.message ?: "Serialization error",
        code = Code.SERIALIZATION_ERROR,
    )

    data object Unknown : ApiException(
        message = "Unknown error",
        code = Code.UNKNOWN,
    )
}
