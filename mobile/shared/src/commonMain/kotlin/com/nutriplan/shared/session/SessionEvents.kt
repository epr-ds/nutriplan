package com.nutriplan.shared.session

import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow

/**
 * Process-wide session signals.
 *
 * Emitted when a token refresh fails: the session is irrecoverably over (the refresh token was
 * rejected or reused), the tokens have been cleared, and navigation must return the user to the
 * auth flow. Kept deliberately small so any layer — the HTTP client, a ViewModel, navigation —
 * can observe it without depending on the others.
 */
object SessionEvents {

    private val _signedOut = MutableSharedFlow<Unit>(extraBufferCapacity = 1)

    /** Fires once per failed refresh (and on explicit sign-out). */
    val signedOut: SharedFlow<Unit> = _signedOut.asSharedFlow()

    /** Signal that the session has ended. Safe to call from any thread. */
    fun emitSignedOut() {
        _signedOut.tryEmit(Unit)
    }
}
