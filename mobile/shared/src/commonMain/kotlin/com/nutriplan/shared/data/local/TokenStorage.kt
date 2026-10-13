package com.nutriplan.shared.data.local

/** Access and refresh token pair kept between app launches. */
data class StoredTokens(
    val accessToken: String,
    val refreshToken: String,
)

/**
 * Persistent storage for the session tokens.
 *
 * Production code uses [SecureTokenStorage] (Android Keystore / iOS Keychain). Tokens must never
 * be written anywhere that is not hardware- or OS-protected.
 */
interface TokenStorage {
    /** The stored tokens, or null if none are stored or they can no longer be read. */
    fun load(): StoredTokens?

    /** Replace the stored tokens. */
    fun save(accessToken: String, refreshToken: String)

    /** Remove the stored tokens (logout). */
    fun clear()
}
