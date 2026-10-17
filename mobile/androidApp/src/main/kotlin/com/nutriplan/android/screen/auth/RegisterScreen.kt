package com.nutriplan.android.screen.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
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
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.component.NutriPlanButton
import com.nutriplan.android.component.NutriPlanTextField
import com.nutriplan.android.di.koinInject
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
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "Create Account",
            style = MaterialTheme.typography.headlineLarge,
            modifier = Modifier.semantics { heading() }
        )

        Spacer(modifier = Modifier.height(32.dp))

        NutriPlanTextField(
            value = state.name,
            onValueChange = onNameChange,
            label = "Name",
            placeholder = "Enter your name",
            isError = state.nameError != null,
            errorMessage = state.nameError.orEmpty()
        )

        Spacer(modifier = Modifier.height(16.dp))

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

        Spacer(modifier = Modifier.height(16.dp))

        NutriPlanTextField(
            value = state.confirmPassword,
            onValueChange = onConfirmPasswordChange,
            label = "Confirm Password",
            placeholder = "Re-enter your password",
            isPassword = true,
            isError = state.confirmPasswordError != null,
            errorMessage = state.confirmPasswordError.orEmpty()
        )

        state.errorMessage?.let {
            Spacer(modifier = Modifier.height(8.dp))
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
            Text("Register")
        }

        Spacer(modifier = Modifier.height(16.dp))

        Row(
            horizontalArrangement = Arrangement.Center,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Already have an account? ")
            TextButton(onClick = onNavigateToLogin) {
                Text("Login")
            }
        }
    }
}
