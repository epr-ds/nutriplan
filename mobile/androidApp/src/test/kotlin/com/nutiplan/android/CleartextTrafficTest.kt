package com.nutiplan.android

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutiplan.android.a11y.TestApplication
import kotlin.test.Test
import kotlin.test.assertTrue
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * Local HTTP origins (`http://10.0.2.2:<port>` / `http://192.168.x.x:<port>`) are how the app reaches
 * the local Dockerized gateway. Android blocks cleartext HTTP on apps targeting API 28+, so the
 * app must opt in via `android:usesCleartextTraffic="true"` for local/dev environments to be
 * reachable from an emulator or a physical device on the same network.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class CleartextTrafficTest {

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    @Test
    fun `local http api origins are reachable`() {
        val flags = context.applicationInfo.flags
        val cleartextAllowed = flags and android.content.pm.ApplicationInfo.FLAG_CLEARTEXT_ALLOWED != 0
        assertTrue(
            "Expected cleartext HTTP to be allowed for local API origins, applicationInfo.flags=$flags",
            cleartextAllowed,
        )
    }
}