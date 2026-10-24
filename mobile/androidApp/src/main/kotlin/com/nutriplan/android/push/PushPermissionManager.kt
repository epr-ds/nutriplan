package com.nutriplan.android.push

import android.Manifest
import android.content.Context
import android.content.SharedPreferences
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import com.nutriplan.shared.notifications.PushPermissionStatus
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** SharedPreferences key marking that the OS permission flow ran at least once. */
private const val PREFS_NAME = "nutriplan_push_permission"

/** Key inside [PREFS_NAME] that marks that the user already went through the prompt. */
private const val KEY_ASKED = "asked"

/**
 * Notification permission state of the app process (NTF-504).
 *
 * The user has not been asked yet ([PushPermissionStatus.NOT_ASKED]), has granted
 * ([PushPermissionStatus.GRANTED]), has refused ([PushPermissionStatus.DENIED]), or — on iOS —
 * accepted quiet/provisional access ([PushPermissionStatus.PROVISIONAL]). The OS answer arrives
 * through [onRequestResult]; [refreshStatus] re-reads the OS state, for example after the user
 * changed the permission in the system settings (the re-prompt path).
 */
class PushPermissionManager(private val appContext: Context) {

    private val preferences: SharedPreferences =
        appContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    private val _status = MutableStateFlow(resolveStatus(granted = false, asked = false))
    val status: StateFlow<PushPermissionStatus> = _status.asStateFlow()

    /**
     * Record the answer of the OS prompt: granted keeps notifications on
     * ([PushPermissionStatus.GRANTED]), refused turns them off ([PushPermissionStatus.DENIED]).
     */
    fun onRequestResult(granted: Boolean) {
        preferences.edit().putBoolean(KEY_ASKED, true).apply()
        _status.value = if (granted) PushPermissionStatus.GRANTED else PushPermissionStatus.DENIED
    }

    /**
     * Re-read the OS permission and refresh the state; called on resume so a permission flipped in
     * the system settings is picked up.
     */
    fun refreshStatus() {
        val granted = ContextCompat.checkSelfPermission(
            appContext,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
        _status.value = resolveStatus(
            granted = granted,
            asked = preferences.getBoolean(KEY_ASKED, false),
        )
    }

    private fun resolveStatus(granted: Boolean, asked: Boolean): PushPermissionStatus = when {
        granted -> PushPermissionStatus.GRANTED
        asked -> PushPermissionStatus.DENIED
        else -> PushPermissionStatus.NOT_ASKED
    }
}