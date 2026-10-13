package com.nutriplan.shared.data.network

import com.nutriplan.shared.data.repository.AuthRepository
import io.ktor.client.HttpClient
import io.ktor.client.plugins.auth.Auth
import io.ktor.client.plugins.auth.providers.BearerTokens
import io.ktor.client.plugins.auth.providers.bearer
import io.ktor.client.plugins.install

/**
 * Configure the auth plugin on the given client with the current token source.
 */
fun configureAuth(
    client: HttpClient,
    authRepository: AuthRepository,
) {
    client.install(Auth) {
        bearer {
            loadTokens {
                BearerTokens(
                    accessToken = authRepository.currentAccessToken ?: "",
                    refreshToken = authRepository.currentRefreshToken ?: "",
                )
            }
            refreshTokens { refreshToken ->
                try {
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
