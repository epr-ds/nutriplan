package com.nutriplan.shared.data.local

/**
 * [TokenStorage] backed by the platform's secure store.
 *
 * - Android: AES-256-GCM with a non-exportable key in the Android Keystore; the ciphertext is kept
 *   in private SharedPreferences. Needs a `Context`.
 * - iOS: Keychain generic passwords, available after first unlock and never synced or migrated
 *   to another device.
 */
expect class SecureTokenStorage : TokenStorage {
    override fun load(): StoredTokens?
    override fun save(accessToken: String, refreshToken: String)
    override fun clear()
}
