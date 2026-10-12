package com.nutriplan.shared.data.network

import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.engine.HttpClientEngineFactory

/**
 * Provides the singleton [HttpClient] instance used throughout the data layer.
 *
 * Call [create] to initialize with a specific engine, or use the default
 * (which delegates to the platform-specific engine factory).
 */
object HttpClientProvider {

    private var instance: HttpClient? = null

    /**
     * Get the configured [HttpClient] instance.
     *
     * @throws IllegalStateException if [create] has not been called.
     */
    val client: HttpClient
        get() = instance
            ?: throw IllegalStateException(
                "HttpClient not initialized. Call HttpClientProvider.create() first.",
            )

    /**
     * Create and configure the [HttpClient] with the given engine.
     *
     * @param engineFactory The platform-specific HTTP engine factory.
     * @param timeoutMillis Optional timeout in milliseconds.
     */
    fun create(
        engineFactory: HttpClientEngineFactory<*>,
        timeoutMillis: Long = 30_000L,
    ) {
        val engine = engineFactory.create()
        instance = HttpClientFactory.create(engine, timeoutMillis)
    }

    /**
     * Create and configure the [HttpClient] with a pre-built engine instance.
     */
    fun create(
        engine: HttpClientEngine,
        timeoutMillis: Long = 30_000L,
    ) {
        instance = HttpClientFactory.create(engine, timeoutMillis)
    }

    /**
     * Reset the client (useful for testing).
     */
    fun reset() {
        instance?.close()
        instance = null
    }
}
