package com.nutriplan.shared.auth

/**
 * OAuth identity providers accepted by the identity service (`POST /auth/oauth/{provider}`).
 *
 * [slug] is the path segment used in the contract.
 */
enum class OAuthProvider(val slug: String) {
    GOOGLE("google"),
    FACEBOOK("facebook"),
    APPLE("apple"),
}

/** A provider-issued id-token (and optional nonce) to exchange with the backend. */
data class OAuthToken(
    val idToken: String,
    val nonce: String? = null,
)

/**
 * Obtains an id-token from a native OAuth provider SDK.
 *
 * Platform implementations live with the app: Android uses Credential Manager / Google Identity,
 * iOS will use Authentication Services (IDN-506). [supportedProviders] reports which providers the
 * platform can actually present so the UI only offers working buttons. [signIn] returns `null` when
 * the user dismisses the consent sheet, so a cancel is not treated as an error.
 */
interface OAuthTokenProvider {

    /** Providers this platform can present. */
    val supportedProviders: Set<OAuthProvider>

    /** Runs native consent for [provider] and returns the id-token, or `null` if cancelled. */
    suspend fun signIn(provider: OAuthProvider): OAuthToken?
}
