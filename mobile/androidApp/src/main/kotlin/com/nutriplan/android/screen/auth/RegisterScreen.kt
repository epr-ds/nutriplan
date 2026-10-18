package com.nutriplan.android.screen.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
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
import com.nutriplan.shared.auth.RegisterUiState
import com.nutriplan.shared.auth.RegisterViewModel
import kotlinx.coroutines.launch

@Composable
fun RegisterScreen(
    onRegisterSuccess: () -> Unit,
    onNavigateToLogin: () -> Unit
) {
    val viewModel = koinInject<RegisterViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    // A brand-new user always lands in onboarding; the session state drives the next destination.
    LaunchedEffect(state.isSuccess) {
        if (state.isSuccess) onRegisterSuccess()
    }

    RegisterScreenContent(
        state = state,
        onNameChange = viewModel::onNameChange,
        onEmailChange = viewModel::onEmailChange,
        onPasswordChange = viewModel::onPasswordChange,
        onConfirmPasswordChange = viewModel::onConfirmPasswordChange,
        onSubmit = { scope.launch { viewModel.submit() } },
        onNavigateToLogin = onNavigateToLogin,
    )
}

/**
 * Stateless registration UI (IDN-503/705). Kept separate from [RegisterScreen] so the accessibility
 * checks can render it directly without the DI graph.
 */
@Composable
internal fun RegisterScreenContent(
    state: RegisterUiState,
    onNameChange: (String) -> Unit,
    onEmailChange: (String) -> Unit,
    onPasswordChange: (String) -> Unit,
    onConfirmPasswordChange: (String) -> Unit,
    onSubmit: () -> Unit,
    onNavigateToLogin: () -> Unit,
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
            text = stringResource(R.string.register_title),
            style = MaterialTheme.typography.headlineLarge,
            modifier = Modifier.semantics { heading() }
        )

        Spacer(modifier = Modifier.height(32.dp))

        NutriPlanTextField(
            value = state.name,
            onValueChange = onNameChange,
            label = stringResource(R.string.register_name_label),
            placeholder = stringResource(R.string.register_name_placeholder),
            isError = state.nameError != null,
            errorMessage = state.nameError?.let { stringResource(it.messageRes()) }.orEmpty()
        )

        Spacer(modifier = Modifier.height(16.dp))

        NutriPlanTextField(
            value = state.email,
            onValueChange = onEmailChange,
            label = stringResource(R.string.register_email_label),
            placeholder = stringResource(R.string.register_email_placeholder),
            isError = state.emailError != null,
            errorMessage = state.emailError?.let { stringResource(it.messageRes()) }.orEmpty()
        )

        Spacer(modifier = Modifier.height(16.dp))

        NutriPlanTextField(
            value = state.password,
            onValueChange = onPasswordChange,
            label = stringResource(R.string.register_password_label),
            placeholder = stringResource(R.string.register_password_placeholder),
            isPassword = true,
            isError = state.passwordError != null,
            errorMessage = state.passwordError?.let { stringResource(it.messageRes()) }.orEmpty()
        )

        Spacer(modifier = Modifier.height(16.dp))

        NutriPlanTextField(
            value = state.confirmPassword,
            onValueChange = onConfirmPasswordChange,
            label = stringResource(R.string.register_confirm_password_label),
            placeholder = stringResource(R.string.register_confirm_password_placeholder),
            isPassword = true,
            isError = state.confirmPasswordError != null,
            errorMessage = state.confirmPasswordError?.let { stringResource(it.messageRes()) }.orEmpty()
        )

        state.error?.let { error ->
            Spacer(modifier = Modifier.height(8.dp))
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
            Text(stringResource(R.string.register_submit))
        }

        Spacer(modifier = Modifier.height(16.dp))

        Row(
            horizontalArrangement = Arrangement.Center,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(stringResource(R.string.register_have_account))
            TextButton(onClick = onNavigateToLogin) {
                Text(stringResource(R.string.register_login_link))
            }
        }
    }
}
