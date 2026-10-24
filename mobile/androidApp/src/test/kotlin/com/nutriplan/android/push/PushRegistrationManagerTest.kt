package com.nutriplan.android.push

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.shared.data.model.Notification
import com.nutriplan.shared.data.model.NotificationPreferences
import com.nutriplan.shared.data.model.RegisteredDevice
import com.nutriplan.shared.data.model.UnreadCountResponse
import com.nutriplan.shared.data.model.UpdateNotificationPreferencesRequest
import com.nutriplan.shared.data.repository.NotificationRepository
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * NTF-505: device-token registration and revocation of the push backend for Android.
 *
 * Runs on the JVM via Robolectric, so the registration and revocation bookkeeping are exercised
 * without an emulator.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class PushRegistrationManagerTest {

    private val context: Context = ApplicationProvider.getApplicationContext()

    @Test
    fun `registering a token stores the resolved device id`() = runBlocking {
        val fake = FakeNotificationRepository()
        val manager = PushRegistrationManager(context, fake)

        manager.register(token = "fcm-token-1")

        assertEquals("android", fake.registeredPlatform)
        assertEquals("fcm-token-1", fake.registeredToken)
        assertEquals("device-1", manager.deviceId)
    }

    @Test
    fun `revoking clears the registered device and calls the backend`() = runBlocking {
        val fake = FakeNotificationRepository()
        val manager = PushRegistrationManager(context, fake)

        manager.register(token = "fcm-token-1")
        manager.revoke()

        assertNull(manager.deviceId)
        assertEquals("device-1", fake.revokedDeviceId)
    }
}

/** Minimal [NotificationRepository] fake: only the registration calls under test are recorded. */
private class FakeNotificationRepository : NotificationRepository {

    var registeredPlatform: String? = null
    var registeredToken: String? = null
    var revokedDeviceId: String? = null

    override suspend fun getNotifications(): List<Notification> = error("not used in these tests")

    override suspend fun getUnreadCount(): UnreadCountResponse = error("not used in these tests")

    override suspend fun markAsRead(notificationId: String) = error("not used in these tests")

    override suspend fun getPreferences(): NotificationPreferences =
        error("not used in these tests")

    override suspend fun updatePreferences(
        request: UpdateNotificationPreferencesRequest,
    ): NotificationPreferences = error("not used in these tests")

    override suspend fun registerDevice(platform: String, token: String): RegisteredDevice {
        registeredPlatform = platform
        registeredToken = token
        return RegisteredDevice(
            id = "device-1",
            platform = platform,
            createdAt = "2026-10-24T00:00:00Z",
            updatedAt = "2026-10-24T00:00:00Z",
        )
    }

    override suspend fun revokeDevice(deviceId: String) {
        revokedDeviceId = deviceId
    }
}