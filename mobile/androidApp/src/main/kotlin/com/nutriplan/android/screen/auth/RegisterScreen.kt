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
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.component.NutriPlanButton
import com.nutriplan.android.component.NutriPlanTextField
import com.nutriplan.android.di.koinInject
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

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "Create Account",
            style = MaterialTheme.typography.headlineLarge
        )

        Spacer(modifier = Modifier.height(32.dp))

        NutriPlanTextField(
            value = state.name,
            onValueChange = viewModel::onNameChange,
            label = "Name",
            placeholder = "Enter your name",
            isError = state.nameError != null,
            errorMessage = state.nameError.orEmpty()
        )

        Spacer(modifier = Modifier.height(16.dp))

        NutriPlanTextField(
            value = state.email,
            onValueChange = viewModel::onEmailChange,
            label = "Email",
            placeholder = "Enter your email",
            isError = state.emailError != null,
            errorMessage = state.emailError.orEmpty()
        )

        Spacer(modifier = Modifier.height(16.dp))

        NutriPlanTextField(
            value = state.password,
            onValueChange = viewModel::onPasswordChange,
            label = "Password",
            placeholder = "Enter your password",
            isPassword = true,
            isError = state.passwordError != null,
            errorMessage = state.passwordError.orEmpty()
        )

        Spacer(modifier = Modifier.height(16.dp))

        NutriPlanTextField(
            value = state.confirmPassword,
            onValueChange = viewModel::onConfirmPasswordChange,
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
                modifier = Modifier.semantics { contentDescription = "Error: $it" }
            )
        }

        Spacer(modifier = Modifier.height(24.dp))

        NutriPlanButton(
            onClick = {
                if (state.canSubmit) {
                    scope.launch { viewModel.submit() }
                }
            },
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
