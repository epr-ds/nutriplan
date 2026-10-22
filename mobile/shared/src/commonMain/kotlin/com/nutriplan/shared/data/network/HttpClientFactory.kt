package com.nutriplan.shared.data.network

import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.repository.AuthRepository
import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.network.sockets.ConnectTimeoutException
import io.ktor.client.network.sockets.SocketTimeoutException
import io.ktor.client.plugins.HttpRequestTimeoutException
import io.ktor.client.plugins.HttpResponseValidator
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.auth.Auth
import io.ktor.client.plugins.auth.providers.BearerTokens
import io.ktor.client.plugins.auth.providers.bearer
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.logging.LogLevel
import io.ktor.client.plugins.logging.Logger
import io.ktor.client.plugins.logging.Logging
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.serialization.kotlinx.json.json
import io.ktor.utils.io.errors.IOException
import kotlinx.serialization.json.Json

/** True for failures of the connection itself, as opposed to an HTTP response from the server. */
internal fun Throwable.isTransportFailure(): Boolean =
    this is IOException ||
        this is HttpRequestTimeoutException ||
        this is ConnectTimeoutException ||
        this is SocketTimeoutException

/**
 * True when the server was reached but took too long to answer (AIA-606): the request or the socket
 * timed out, or a gateway gave up (HTTP 504). Not when it could not be reached at all, which is
 * being offline.
 */
internal fun Throwable.isResponseTimeout(): Boolean {
    if (this is ApiException.HttpError) return statusCode == HTTP_GATEWAY_TIMEOUT
    val cause = (this as? ApiException.NetworkError)?.errorCause ?: this
    return cause is HttpRequestTimeoutException || cause is SocketTimeoutException
}

private const val HTTP_GATEWAY_TIMEOUT = 504

/** Sends Ktor's HTTP logs to stdout so each platform's log pipeline can capture them. */
private val httpLogger = object : Logger {
    override fun log(message: String) {
        println("[nutriplan-http] $message")
    }
}

/**
 * Factory for creating a configured Ktor [HttpClient] instance.
 *
 * The client is configured with:
 * - Content negotiation with kotlinx.serialization JSON
 * - Default headers (Accept, Content-Type)
 * - Timeout settings
 * - Auth-header-redacted logging
 * - Optional auth plugin for bearer token handling
 */
object HttpClientFactory {

    /**
     * Create a new [HttpClient] with the given engine.
     *
     * @param engine The HTTP engine to use (OkHttp on Android, Darwin on iOS).
     * @param authRepository Optional auth repository for bearer token handling.
     * @param timeoutMillis Optional timeout in milliseconds; defaults to 30 seconds.
     */
    fun create(
        engine: HttpClientEngine,
        authRepository: AuthRepository? = null,
        timeoutMillis: Long = 30_000L,
    ): HttpClient {
        return HttpClient(engine) {
            install(ContentNegotiation) {
                json(
                    Json {
                        isLenient = true
                        ignoreUnknownKeys = true
                        prettyPrint = false
                        encodeDefaults = true
                    },
                )
            }

            install(HttpTimeout) {
                connectTimeoutMillis = timeoutMillis
                socketTimeoutMillis = timeoutMillis
                requestTimeoutMillis = timeoutMillis
            }

            // Transport failures (no connection, DNS failure, timeouts) surface as
            // ApiException.NetworkError, so callers can tell "offline" from "the server said no"
            // (see ApiFailure) and the offline cache fallback can actually trigger.
            HttpResponseValidator {
                handleResponseExceptionWithRequest { cause, _ ->
                    if (cause.isTransportFailure()) throw ApiException.NetworkError(errorCause = cause)
                }
            }

            // Auth-header-redacted logging (IDN-402): log request/response headers only (never
            // bodies, which can carry credentials), with bearer tokens, cookies, and API keys
            // masked by isSensitiveHeader.
            install(Logging) {
                logger = httpLogger
                level = LogLevel.HEADERS
                sanitizeHeader { header -> isSensitiveHeader(header) }
            }

            defaultRequest {
                url(ApiConfig.BASE_URL)
                headers.append(HttpHeaders.ContentType, ContentType.Application.Json.toString())
                headers.append(HttpHeaders.Accept, ContentType.Application.Json.toString())
            }

            if (authRepository != null) {
                val refresher = BearerTokenRefresher(authRepository)
                install(Auth) {
                    bearer {
                        loadTokens {
                            BearerTokens(
                                accessToken = authRepository.currentAccessToken ?: "",
                                refreshToken = authRepository.currentRefreshToken ?: "",
                            )
                        }
                        refreshTokens {
                            oldTokens?.refreshToken?.let { refresher.refresh(it) }
                        }
                    }
                }
            }
        }
    }
}
