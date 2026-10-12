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
        fun create(message: String, code: Code): ApiException =
            ApiException(body = null, message = message, code = code)
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
        val cause: Throwable?,
    ) : ApiException(
        body = null,
        message = cause?.message ?: "Network error",
        code = Code.NETWORK_ERROR,
    ) {
        override val cause: Throwable? = cause
    }

    data class SerializationError(
        val cause: Throwable?,
    ) : ApiException(
        body = null,
        message = cause?.message ?: "Serialization error",
        code = Code.SERIALIZATION_ERROR,
    ) {
        override val cause: Throwable? = cause
    }

    object Unknown : ApiException(
        body = null,
        message = "Unknown error",
        code = Code.UNKNOWN,
    )
}
