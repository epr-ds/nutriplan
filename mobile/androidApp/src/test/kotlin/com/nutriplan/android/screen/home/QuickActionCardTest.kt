package com.nutriplan.android.screen.home

import android.content.Context
import androidx.compose.ui.test.assertExists
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.ui.theme.NutriPlanTheme
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.i18n.Icons
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * F12 — QuickActionCard clickable Card has an accessible name for screen readers (WCAG 4.1.2).
 * Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], qualifiers = "en-rUS", application = TestApplication::class)
class QuickActionCardTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private fun render(label: String) {
        compose.setContent {
            NutriPlanTheme {
                QuickActionCard(
                    icon = Icons.Default.CalendarMonth,
                    label = label,
                    onClick = {},
                )
            }
        }
    }

    @Test
    fun `card has an accessible name for screen readers`() {
        val label = str(R.string.meal_plans_all)
        render(label)

        // The clickable Card must announce its label as an accessible name.
        compose.onNodeWithContentDescription(label).assertExists()
    }

    @Test
    fun `card is not announced as just "Card"`() {
        val label = str(R.string.meal_plans_all)
        render(label)

        // The Card's semantic content should contain the label text.
        compose.onNodeWithText(label).assertIsDisplayed()
    }
}
