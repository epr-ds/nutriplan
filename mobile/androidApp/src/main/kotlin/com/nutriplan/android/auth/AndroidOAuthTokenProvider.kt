package com.nutriplan.android.auth

import android.app.Activity
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.nutriplan.shared.auth.OAuthProvider
import com.nutriplan.shared.auth.OAuthToken
import com.nutriplan.shared.auth.OAuthTokenProvider

/**
 * Android [OAuthTokenProvider] backed by Credential Manager (Google Identity).
 *
 * The server (web) client ID comes from the build (`GOOGLE_SERVER_CLIENT_ID`, per-env secret
 * IDN-803). When it is blank the flow is not configured, so [supportedProviders] is empty and the
 * UI hides the button rather than showing one that cannot work.
 *
 * Facebook and Apple are not offered natively on Android (Apple requires a web flow), so only
 * Google is presented here.
 */
class AndroidOAuthTokenProvider(
    private val serverClientId: String,
    private val activityProvider: () -> Activity? = { CurrentActivity.get() },
) : OAuthTokenProvider {

    override val supportedProviders: Set<OAuthProvider> =
        if (serverClientId.isBlank()) emptySet() else setOf(OAuthProvider.GOOGLE)

    override suspend fun signIn(provider: OAuthProvider): OAuthToken? {
        if (provider != OAuthProvider.GOOGLE) return null
        val activity = activityProvider() ?: return null

        val credentialManager = CredentialManager.create(activity)
        val googleIdOption = GetGoogleIdOption.Builder()
            .setFilterByAuthorizedAccounts(false)
            .setServerClientId(serverClientId)
            .setAutoSelectEnabled(false)
            .build()
        val request = GetCredentialRequest.Builder()
            .addCredentialOption(googleIdOption)
            .build()

        val credential = try {
            credentialManager.getCredential(context = activity, request = request).credential
        } catch (e: GetCredentialCancellationException) {
            // The user dismissed the consent sheet.
            return null
        }

        return if (credential is CustomCredential &&
            credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL
        ) {
            OAuthToken(idToken = GoogleIdTokenCredential.createFrom(credential.data).idToken)
        } else {
            null
        }
    }
}
