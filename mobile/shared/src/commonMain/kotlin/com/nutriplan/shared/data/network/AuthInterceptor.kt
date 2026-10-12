package com.nutriplan.shared.data.network

import com.nutriplan.shared.data.repository.AuthRepository
import io.ktor.client.HttpClient
import io.ktor.client.plugins.HttpClientPlugin
import io.ktor.client.plugins.auth.Auth
import io.ktor.client.plugins.auth.providers.BearerTokens
import io.ktor.client.plugins.auth.providers.bearer
import io.ktor.client.request.HttpRequestPipeline
import io.ktor.http.HttpMethod

/**
 * Ktor plugin that intercepts requests to attach the current token.
 *
 * Handles 401 responses by attempting a token refresh before retrying.
 * If refresh fails, clears tokens and re-throws the 401.
 */
object AuthInterceptor {

    /** Ktor plugin instance. */
    val plugin: HttpClientPlugin<*, *> = createAuthPlugin()

    private fun createAuthPlugin(): HttpClientPlugin<AuthConfig, AuthConfig> = object : HttpClientPlugin<AuthConfig, AuthConfig> {
        override val key = HttpClientPlugin.NamedKey("authInterceptor")

        override fun install(configuration: AuthConfig, scope: HttpClient) {
            scope.requestPipeline.intercept(HttpRequestPipeline.Before) {
                val token = configuration.authRepository?.currentAccessToken
                if (!token.isNullOrEmpty()) {
                    context.headers.append("Authorization", "Bearer $token")
                }
            }
        }
    }

    /**
     * Configure the auth plugin with the current token source.
     */
    fun configureAuth(
        client: HttpClient,
        authRepository: AuthRepository,
    ) {
        client.createPlugin(Auth).apply {
            bearer {
                loadTokens {
                    BearerTokens(
                        accessToken = authRepository.currentAccessToken ?: "",
                        refreshToken = authRepository.currentRefreshToken ?: "",
                    )
                }
                refreshTokens {
                    try {
                        val refreshToken = it.refreshToken
                        val response = authRepository.refreshToken(refreshToken)
                        authRepository.updateTokens(response.accessToken, response.refreshToken)
                        BearerTokens(response.accessToken, response.refreshToken)
                    } catch (e: Exception) {
                        authRepository.clearTokens()
                        throw e
                    }
                }
            }
        }
    }
}

/** Configuration for the auth interceptor. */
class AuthConfig {
    var authRepository: AuthRepository? = null
}