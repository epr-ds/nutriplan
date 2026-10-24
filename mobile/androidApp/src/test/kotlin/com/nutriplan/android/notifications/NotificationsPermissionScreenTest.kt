package com.nutriplan.android.notifications

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.screen.notifications.NotificationsPermissionDeniedScreen
import com.nutriplan.android.screen.notifications.NotificationsPermissionScreen
import com.nutriplan.android.screen.notifications.NotificationsPermissionTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * NTF-504: the in-app permission screens render their actions before the OS prompt runs.
 *
 * Runs on the JVM via Robolectric, so the priming and refusal states are exercised without an
 * emulator.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class NotificationsPermissionScreenTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `the priming screen lets the user allow or defer`() {
        var allowed = 0
        var dismissed = 0

        compose.setContent {
            NutriPlanTheme {
                NotificationsPermissionScreen(
                    onAllow = { allowed++ },
                    onNotNow = { dismissed++ },
                )
            }
        }

        compose.onNodeWithTag(NotificationsPermissionTestTags.ALLOW).performClick()
        assertEquals(1, allowed)

        compose.onNodeWithTag(NotificationsPermissionTestTags.NOT_NOW).performClick()
        assertEquals(1, dismissed)
    }

    @Test
    fun `the denied screen offers the settings re-prompt`() {
        var opened = 0

        compose.setContent {
            NutriPlanTheme {
                NotificationsPermissionDeniedScreen(onOpenSettings = { opened++ })
            }
        }

        compose.onNodeWithTag(NotificationsPermissionTestTags.OPEN_SETTINGS).performClick()
        assertEquals(1, opened)
    }
}