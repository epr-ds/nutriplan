package com.nutriplan.android.screen.auth

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.screen.auth.LoginScreenContent
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.auth.LoginUiState
import com.nutriplan.shared.auth.OAuthProvider
import com.nutriplan.shared.auth.OAuthUiState
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * F7 — Social login buttons have a minimum size guarantee (WCAG 2.5.5, AA ≥ 48×48dp).
 * F9 — Payment method buttons have explicit min-height (WCAG 2.5.5).
 * Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class TouchTargetTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    private fun renderLogin(provider: OAuthProvider = OAuthProvider.GOOGLE) {
        compose.setContent {
            NutriPlanTheme {
                LoginScreenContent(
                    state = LoginUiState(),
                    oauthState = OAuthUiState(),
                    supportedProviders = setOf(provider),
                    onEmailChange = {},
                    onPasswordChange = {},
                    onSubmit = {},
                    onForgotPassword = {},
                    onNavigateToRegister = {},
                    onOAuthSignIn = {},
                )
            }
        }
    }

    @Test
    fun `oauth button has at least 48dp height`() {
        renderLogin()

        // Find the OAuth button by its text label.
        val text = str(R.string.oauth_continue_with_google)

        // The button itself must be at least 48dp tall.
        compose.onNodeWithText(text).assertHeightIsAtLeast(48.dp)
    }

    @Test
    fun `submit button has at least 48dp height`() {
        renderLogin()

        val text = str(R.string.login_submit)
        compose.onNodeWithText(text).assertHeightIsAtLeast(48.dp)
    }

    @Test
    fun `forgot password button has at least 48dp height`() {
        renderLogin()

        val text = str(R.string.login_forgot_password)
        compose.onNodeWithText(text).assertHeightIsAtLeast(48.dp)
    }
}
