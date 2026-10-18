package com.nutriplan.android.screen.auth

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.android.component.NutriPlanButton
import com.nutriplan.android.component.NutriPlanTextField
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.messageRes
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
            // F30: scroll so the form stays usable with large font sizes / dynamic type (WCAG 1.4.4)
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = stringResource(R.string.login_title),
            style = MaterialTheme.typography.headlineLarge,
            modifier = Modifier.semantics { heading() }
        )

        Spacer(modifier = Modifier.height(32.dp))

        NutriPlanTextField(
            value = state.email,
            onValueChange = onEmailChange,
            label = stringResource(R.string.login_email_label),
            placeholder = stringResource(R.string.login_email_placeholder),
            isError = state.emailError != null,
            errorMessage = state.emailError?.let { stringResource(it.messageRes()) }.orEmpty()
        )

        Spacer(modifier = Modifier.height(16.dp))

        NutriPlanTextField(
            value = state.password,
            onValueChange = onPasswordChange,
            label = stringResource(R.string.login_password_label),
            placeholder = stringResource(R.string.login_password_placeholder),
            isPassword = true,
            isError = state.passwordError != null,
            errorMessage = state.passwordError?.let { stringResource(it.messageRes()) }.orEmpty()
        )

        Spacer(modifier = Modifier.height(8.dp))

        TextButton(
            onClick = onForgotPassword,
            modifier = Modifier.align(Alignment.End)
        ) {
            Text(stringResource(R.string.login_forgot_password))
        }

        state.error?.let { error ->
            Spacer(modifier = Modifier.height(8.dp))
            // F28: live region so screen readers announce form errors (WCAG 3.3.1, 4.1.3)
            Text(
                text = stringResource(error.messageRes()),
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
            Text(stringResource(R.string.login_submit))
        }

        Spacer(modifier = Modifier.height(16.dp))

        Row(
            horizontalArrangement = Arrangement.Center,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(stringResource(R.string.login_no_account))
            TextButton(onClick = onNavigateToRegister) {
                Text(stringResource(R.string.login_register_link))
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

            oauthState.error?.let { error ->
                Text(
                    text = stringResource(error.messageRes()),
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }
                )
            }
        }
    }
}

@Composable
private fun oauthProviderLabel(provider: OAuthProvider): String = when (provider) {
    OAuthProvider.GOOGLE -> stringResource(R.string.oauth_continue_with_google)
    OAuthProvider.FACEBOOK -> stringResource(R.string.oauth_continue_with_facebook)
    OAuthProvider.APPLE -> stringResource(R.string.oauth_continue_with_apple)
}
