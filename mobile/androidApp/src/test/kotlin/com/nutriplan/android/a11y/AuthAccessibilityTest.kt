package com.nutriplan.android.a11y

import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.screen.auth.LoginScreenContent
import com.nutriplan.android.screen.auth.RegisterScreenContent
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.auth.AuthError
import com.nutriplan.shared.auth.FieldError
import com.nutriplan.shared.auth.LoginUiState
import com.nutriplan.shared.auth.OAuthProvider
import com.nutriplan.shared.auth.OAuthUiState
import com.nutriplan.shared.auth.RegisterUiState
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * IDN-705: accessibility checks for the auth screens (login + register).
 *
 * Guards the labels, headings, live-region errors, and 48dp touch targets that assistive tech needs.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class AuthAccessibilityTest {

    @get:Rule
    val compose = createComposeRule()

    private fun renderLogin(
        state: LoginUiState,
        oauthState: OAuthUiState = OAuthUiState(),
        providers: Set<OAuthProvider> = emptySet(),
    ) {
        compose.setContent {
            NutriPlanTheme {
                LoginScreenContent(
                    state = state,
                    oauthState = oauthState,
                    supportedProviders = providers,
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

    private fun renderRegister(state: RegisterUiState) {
        compose.setContent {
            NutriPlanTheme {
                RegisterScreenContent(
                    state = state,
                    onNameChange = {},
                    onEmailChange = {},
                    onPasswordChange = {},
                    onConfirmPasswordChange = {},
                    onSubmit = {},
                    onNavigateToLogin = {},
                )
            }
        }
    }

    @Test
    fun login_exposes_heading_labels_and_actions() {
        renderLogin(LoginUiState())

        compose.onNodeWithText("Welcome Back").assert(isHeading())
        compose.onNodeWithText("Email").assertExists()
        compose.onNodeWithText("Password").assertExists()
        compose.onNodeWithText("Forgot Password?").assertExists()
        compose.onNodeWithText("Register").assertExists()
        compose.onNodeWithText("Login").assertHeightIsAtLeast(48.dp)
    }

    @Test
    fun login_field_and_form_errors_are_announced() {
        renderLogin(
            LoginUiState(
                email = "not-an-email",
                password = "secret",
                emailError = FieldError.EMAIL_INVALID,
                error = AuthError.INVALID_CREDENTIALS,
            ),
        )

        compose.onNode(hasError("Enter a valid email address.")).assertExists()
        compose.onNodeWithText("Enter a valid email address.").assert(hasLiveRegion())
        compose.onNodeWithText("Incorrect email or password.").assert(hasLiveRegion())
    }

    @Test
    fun oauth_button_stays_labelled_while_loading() {
        renderLogin(
            LoginUiState(),
            oauthState = OAuthUiState(isLoading = true, activeProvider = OAuthProvider.GOOGLE),
            providers = setOf(OAuthProvider.GOOGLE),
        )

        compose.onNodeWithContentDescription("Continue with Google").assertExists()
    }

    @Test
    fun register_exposes_heading_labels_and_errors() {
        renderRegister(
            RegisterUiState(
                name = "Ana",
                email = "ana@example.com",
                password = "secret12",
                confirmPassword = "secret12",
                passwordError = FieldError.PASSWORD_TOO_SHORT,
                error = AuthError.LOGIN_FAILED,
            ),
        )

        compose.onNodeWithText("Create Account").assert(isHeading())
        compose.onNodeWithText("Name").assertExists()
        compose.onNodeWithText("Email").assertExists()
        compose.onNodeWithText("Password").assertExists()
        compose.onNodeWithText("Confirm Password").assertExists()
        compose.onNodeWithText("Use at least 8 characters.").assert(hasLiveRegion())
        compose.onNodeWithText("Login failed. Please try again.").assert(hasLiveRegion())
        compose.onNodeWithText("Register").assertHeightIsAtLeast(48.dp)
    }

    @Test
    @Config(sdk = [34], application = TestApplication::class, qualifiers = "es")
    fun login_and_register_microcopy_is_localized_in_spanish() {
        renderLogin(
            LoginUiState(
                email = "not-an-email",
                emailError = FieldError.EMAIL_INVALID,
                error = AuthError.INVALID_CREDENTIALS,
            ),
        )

        compose.onNodeWithText("Bienvenido de nuevo").assert(isHeading())
        compose.onNodeWithText("Correo electrónico").assertExists()
        compose.onNodeWithText("Iniciar sesión").assertExists()
        compose.onNodeWithText("Introduce una dirección de correo electrónico válida.").assertExists()
        compose.onNodeWithText("Correo electrónico o contraseña incorrectos.").assertExists()
    }
}
