package com.nutriplan.android.push

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.shared.notifications.PushPermissionStatus
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * NTF-504: the notification permission state transitions of the Android push permission manager.
 *
 * Runs on the JVM via Robolectric, so the OS-prompt answers are exercised without an emulator.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class PushPermissionManagerTest {

    private val context: Context = ApplicationProvider.getApplicationContext()

    @Test
    fun `an allow answer keeps notifications on`() {
        val manager = PushPermissionManager(context)

        manager.onRequestResult(granted = true)

        assertEquals(PushPermissionStatus.GRANTED, manager.status.value)
    }

    @Test
    fun `a refuse answer turns notifications off`() {
        val manager = PushPermissionManager(context)

        manager.onRequestResult(granted = false)

        assertEquals(PushPermissionStatus.DENIED, manager.status.value)
    }

    @Test
    fun `a refused permission stays refused until the user re-enables`() {
        val manager = PushPermissionManager(context)

        manager.onRequestResult(granted = false)
        manager.refreshStatus()

        // The OS still reports the permission as not granted, and the user already went through
        // the prompt, so the state stays denied until the user re-enables it in the settings.
        assertEquals(PushPermissionStatus.DENIED, manager.status.value)
    }
}