package com.nutriplan.android.push

import android.content.Context
import android.content.SharedPreferences
import com.google.firebase.messaging.FirebaseMessaging
import com.nutriplan.shared.data.repository.NotificationRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.koin.core.context.GlobalContext

/** SharedPreferences file that remembers this install's push device registration. */
private const val PREFS_NAME = "nutriplan_push_registration"

/** SharedPreferences key holding the registered device id of this install. */
private const val KEY_DEVICE_ID = "device_id"

/** Platform label used when registering the token with the backend (NTF-501). */
private const val PLATFORM_ANDROID = "android"

/**
 * Device-token registration for push notifications (NTF-505).
 *
 * Captures the FCM token the platform hands over and registers it with the backend through the
 * shared notification repository (NTF-302, `POST /notifications/devices`): the token is the
 * registration's identity, so the endpoint is idempotent and a token refresh replaces the previous
 * registration instead of adding another. The returned device id is remembered so the registration
 * can be revoked again when the session ends (logout).
 *
 * All backend traffic runs off the main thread and swallows failures: a push that cannot be
 * registered right now (offline, transient backend error) must never take the app down, the
 * delivery path prunes dead tokens anyway.
 */
class PushRegistrationManager(
    private val appContext: Context,
    private val repository: NotificationRepository =
        GlobalContext.get().get<NotificationRepository>()
) {
    private val preferences: SharedPreferences =
        appContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    /** The registered device id of this install; null before the first successful registration. */
    var deviceId: String? = preferences.getString(KEY_DEVICE_ID, null)

    /** Register a FCM token with the backend and remember the device id it resolved to. */
    suspend fun register(token: String) {
        runCatching {
            val device = repository.registerDevice(platform = PLATFORM_ANDROID, token = token)
            deviceId = device.id
            preferences.edit().putString(KEY_DEVICE_ID, deviceId).apply()
        }
    }

    /**
     * Hand the freshly issued FCM token to the backend (NTF-505): called right after a successful
     * login or registration, before the session starts receiving pushes. The token task result is
     * delivered on a background scope because the listener is not suspend.
     */
    fun registerCurrentToken() {
        val tokenTask = FirebaseMessaging.getInstance().getToken()
        tokenTask.addOnSuccessListener { token ->
            CoroutineScope(SupervisorJob() + Dispatchers.IO).launch { register(token) }
        }
        tokenTask.addOnFailureListener { }
    }

    /**
     * Revoke the registered device (logout). The backend answers 204 with no body; failures are
     * best-effort because logging out must never be blocked by the push backend.
     */
    suspend fun revoke() {
        val storedDeviceId = deviceId
        deviceId = null
        preferences.edit().remove(KEY_DEVICE_ID).apply()
        storedDeviceId?.let { deviceIdToRevoke ->
            runCatching { repository.revokeDevice(deviceId = deviceIdToRevoke) }
        }
    }
}