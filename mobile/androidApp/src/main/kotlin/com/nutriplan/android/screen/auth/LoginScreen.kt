package com.nutriplan.android.screen.auth

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.component.NutriPlanButton
import com.nutriplan.android.component.NutriPlanTextField
import com.nutriplan.android.di.koinInject
import com.nutriplan.shared.auth.LoginUiState
import com.nutriplan.shared.auth.LoginViewModel
import com.nutriplan.shared.auth.OAuthProvider
import com.nutriplan.shared.auth.OAuthUiState
import com.nutriplan.shared.auth.OAuthViewModel
import kotlinx.coroutines.launch

@Composable
fun LoginScreen(
    onLoginSuccess: () -> Unit,
    onNavigateToRegister: () -> Unit,
    onNavigateToForgotPassword: () -> Unit
) {
    val viewModel = koinInject<LoginViewModel>()
    val oauthViewModel = koinInject<OAuthViewModel>()
    val state by viewModel.state.collectAsState()
    val oauthState by oauthViewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    // Route per session state: a successful sign-in advances the session (onboarding or main).
    LaunchedEffect(state.isSuccess) {
        if (state.isSuccess) onLoginSuccess()
    }
    LaunchedEffect(oauthState.isSuccess) {
        if (oauthState.isSuccess) onLoginSuccess()
    }

    LoginScreenContent(
        state = state,
        oauthState = oauthState,
        supportedProviders = oauthViewModel.supportedProviders,
        onEmailChange = viewModel::onEmailChange,
        onPasswordChange = viewModel::onPasswordChange,
        onSubmit = { scope.launch { viewModel.submit() } },
        onForgotPassword = onNavigateToForgotPassword,
        onNavigateToRegister = onNavigateToRegister,
        onOAuthSignIn = { provider -> scope.launch { oauthViewModel.signIn(provider) } },
    )
}

/**
 * Stateless login UI (IDN-501/705). Kept separate from [LoginScreen] so the accessibility checks
 * can render it directly without the DI graph.
 */
@Composable
internal fun LoginScreenContent(
    state: LoginUiState,
    oauthState: OAuthUiState,
    supportedProviders: Set<OAuthProvider>,
    onEmailChange: (String) -> Unit,
    onPasswordChange: (String) -> Unit,
    onSubmit: () -> Unit,
    onForgotPassword: () -> Unit,
    onNavigateToRegister: () -> Unit,
    onOAuthSignIn: (OAuthProvider) -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "Welcome Back",
            style = MaterialTheme.typography.headlineLarge,
            modifier = Modifier.semantics { heading() }
        )

        Spacer(modifier = Modifier.height(32.dp))

        NutriPlanTextField(
            value = state.email,
            onValueChange = onEmailChange,
            label = "Email",
            placeholder = "Enter your email",
            isError = state.emailError != null,
            errorMessage = state.emailError.orEmpty()
        )

        Spacer(modifier = Modifier.height(16.dp))

        NutriPlanTextField(
            value = state.password,
            onValueChange = onPasswordChange,
            label = "Password",
            placeholder = "Enter your password",
            isPassword = true,
            isError = state.passwordError != null,
            errorMessage = state.passwordError.orEmpty()
        )

        Spacer(modifier = Modifier.height(8.dp))

        TextButton(
            onClick = onForgotPassword,
            modifier = Modifier.align(Alignment.End)
        ) {
            Text("Forgot Password?")
        }

        state.errorMessage?.let {
            Spacer(modifier = Modifier.height(8.dp))
            // F28: live region so screen readers announce form errors (WCAG 3.3.1, 4.1.3)
            Text(
                text = it,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }
            )
        }

        Spacer(modifier = Modifier.height(24.dp))

        NutriPlanButton(
            onClick = onSubmit,
            isLoading = state.isLoading,
            isEnabled = state.canSubmit,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Login")
        }

        Spacer(modifier = Modifier.height(16.dp))

        Row(
            horizontalArrangement = Arrangement.Center,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Don't have an account? ")
            TextButton(onClick = onNavigateToRegister) {
                Text("Register")
            }
        }

        // IDN-505: OAuth buttons, limited to the providers this platform can present.
        if (supportedProviders.isNotEmpty()) {
            Spacer(modifier = Modifier.height(16.dp))

            supportedProviders.forEach { provider ->
                val label = oauthProviderLabel(provider)
                OutlinedButton(
                    onClick = { onOAuthSignIn(provider) },
                    enabled = oauthState.canSubmit,
                    modifier = Modifier
                        .fillMaxWidth()
                        .widthIn(min = 48.dp)
                ) {
                    if (oauthState.isLoading && oauthState.activeProvider == provider) {
                        CircularProgressIndicator(
                            modifier = Modifier
                                .size(18.dp)
                                // F29: keep the button labelled while the spinner replaces its text
                                .semantics { contentDescription = label },
                            strokeWidth = 2.dp
                        )
                    } else {
                        Text(label)
                    }
                }
                Spacer(modifier = Modifier.height(8.dp))
            }

            oauthState.errorMessage?.let { message ->
                Text(
                    text = message,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }
                )
            }
        }
    }
}

private fun oauthProviderLabel(provider: OAuthProvider): String = when (provider) {
    OAuthProvider.GOOGLE -> "Continue with Google"
    OAuthProvider.FACEBOOK -> "Continue with Facebook"
    OAuthProvider.APPLE -> "Continue with Apple"
}
