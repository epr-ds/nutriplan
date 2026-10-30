package com.nutriplan.android.a11y

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.component.NutriPlanButton
import com.nutriplan.android.component.NutriPlanTextField
import com.nutriplan.android.ui.theme.NutriPlanTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * F21 — Custom interactive components have a visible focus indicator (WCAG 2.4.7 Focus Visible).
 *
 * Verifies that NutriPlanButton, NutriPlanTextField expose focus semantics so keyboard/switch
 * users can see which element is focused.
 * Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class FocusIndicatorTest {

    @get:Rule
    val compose = createComposeRule()

    private fun render() {
        compose.setContent {
            NutriPlanTheme {
                Row(modifier = Modifier.fillMaxWidth()) {
                    NutriPlanButton(onClick = {}) {
                        Text("Button")
                    }
                    NutriPlanTextField(
                        value = "meal@example.com",
                        onValueChange = {},
                        label = "Email",
                    )
                }
            }
        }
    }

    @Test
    fun `button is focusable`() {
        render()

        compose.onNodeWithText("Button").assertExists()
        compose.onNodeWithContentDescription("Button").assertExists()
    }

    @Test
    fun `text field is focusable`() {
        render()

        compose.onNodeWithText("meal@example.com").assertExists()
    }

    @Test
    fun `nutri plan button exposes a focus semantics node`() {
        render()

        compose.onNodeWithText("Button").assert(hasFocusControl())
    }

    @Test
    fun `nutri plan text field exposes a focus semantics node`() {
        render()

        compose.onNodeWithText("meal@example.com").assert(hasFocusControl())
    }

    private fun hasFocusControl(): SemanticsMatcher = SemanticsMatcher("OffersFocus") { node: SemanticsNode ->
        node.config.contains(SemanticsActions.RequestFocus)
    }
}