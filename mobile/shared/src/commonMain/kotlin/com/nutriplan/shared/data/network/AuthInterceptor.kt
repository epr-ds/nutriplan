package com.nutriplan.shared.data.network

import com.nutriplan.shared.data.repository.AuthRepository
import io.ktor.client.HttpClient
import io.ktor.client.plugins.auth.Auth
import io.ktor.client.plugins.auth.providers.BearerTokens
import io.ktor.client.plugins.auth.providers.bearer

/**
 * Return a copy of [client] with the auth plugin configured for the current token source.
 */
fun configureAuth(
    client: HttpClient,
    authRepository: AuthRepository,
): HttpClient {
    val refresher = BearerTokenRefresher(authRepository)
    return client.config {
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
