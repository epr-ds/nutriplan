package com.nutriplan.shared.data.network

import com.nutriplan.shared.data.ApiConfig
import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

/**
 * Factory for creating a configured Ktor [HttpClient] instance.
 *
 * The client is configured with:
 * - Content negotiation with kotlinx.serialization JSON
 * - Default headers (Accept, Content-Type)
 * - Timeout settings
 * - [AuthInterceptor] for bearer token handling
 */
object HttpClientFactory {

    /**
     * Create a new [HttpClient] with the given engine.
     *
     * @param engine The HTTP engine to use (OkHttp on Android, Darwin on iOS).
     * @param timeoutMillis Optional timeout in milliseconds; defaults to 30 seconds.
     */
    fun create(
        engine: HttpClientEngine,
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

            defaultRequest {
                url(ApiConfig.BASE_URL)
                headers.append(HttpHeaders.ContentType, ContentType.Application.Json.toString())
                headers.append(HttpHeaders.Accept, ContentType.Application.Json.toString())
            }

            install(AuthInterceptor)
        }
    }
}
