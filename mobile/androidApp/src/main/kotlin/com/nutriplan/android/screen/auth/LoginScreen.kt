package com.nutriplan.android.screen.auth

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.background
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.Status
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.nutriplan.android.component.NutriPlanButton
import com.nutriplan.android.component.NutriPlanTextField
import com.nutriplan.android.di.koinInject
import com.nutriplan.shared.data.model.LoginRequest
import com.nutriplan.shared.data.repository.toAuthErrorMessage
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

@Composable
fun LoginScreen(
    onLoginSuccess: () -> Unit,
    onNavigateToRegister: () -> Unit,
    onNavigateToForgotPassword: () -> Unit
) {
    val authRepository = koinInject<com.nutriplan.shared.data.repository.AuthRepository>()
    val scope = rememberCoroutineScope()

    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        // Check if user is already logged in
        if (authRepository.isAuthenticated) {
            onLoginSuccess()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "Welcome Back",
            style = MaterialTheme.typography.headlineLarge
        )

        Spacer(modifier = Modifier.height(32.dp))

        NutriPlanTextField(
            value = email,
            onValueChange = { email = it },
            label = "Email",
            placeholder = "Enter your email",
            // F29: Add keyboard type hint for correct mobile keyboard (WCAG 3.3.2)
            keyboardType = androidx.compose.ui.text.input.KeyboardType.Email
        )

        Spacer(modifier = Modifier.height(16.dp))

        NutriPlanTextField(
            value = password,
            onValueChange = { password = it },
            label = "Password",
            placeholder = "Enter your password",
            isPassword = true
        )

        Spacer(modifier = Modifier.height(8.dp))

        TextButton(
            onClick = onNavigateToForgotPassword,
            modifier = Modifier.align(Alignment.End)
        ) {
            Text("Forgot Password?")
        }

        errorMessage?.let {
            Spacer(modifier = Modifier.height(8.dp))
            // F28: Add live region semantics for error announcements (WCAG 3.3.1, 4.1.3)
            Text(
                text = it,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.semantics { role = Role.Status; contentDescription = "Error: $it" }
            )
        }

        Spacer(modifier = Modifier.height(24.dp))

        NutriPlanButton(
            onClick = {
                if (!isLoading) {
                    if (email.isBlank() || password.isBlank()) {
                        errorMessage = "Enter your email and password."
                    } else {
                        isLoading = true
                        errorMessage = null
                        scope.launch {
                            try {
                                authRepository.login(LoginRequest(email.trim(), password))
                                onLoginSuccess()
                            } catch (e: CancellationException) {
                                throw e
                            } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
                                errorMessage = e.toAuthErrorMessage()
                            } finally {
                                isLoading = false
                            }
                        }
                    }
                }
            },
            isLoading = isLoading,
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

        Spacer(modifier = Modifier.height(24.dp))

        // Social login buttons
        Row(
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            // F7: Add minimum touch target (≥48dp) and content description (WCAG 2.5.5, 4.1.2)
            Box(
                modifier = Modifier
                    .weight(1f)
                    .aspectRatio(1f)
                    .minimumWidth(48.dp)
                    .background(
                        MaterialTheme.colorScheme.surfaceVariant,
                        MaterialTheme.shapes.medium
                    ),
                contentAlignment = Alignment.Center
            ) {
                Text("G")
            }
            // F7: Add minimum touch target (≥48dp) and content description (WCAG 2.5.5, 4.1.2)
            Box(
                modifier = Modifier
                    .weight(1f)
                    .aspectRatio(1f)
                    .minimumWidth(48.dp)
                    .background(
                        MaterialTheme.colorScheme.surfaceVariant,
                        MaterialTheme.shapes.medium
                    ),
                contentAlignment = Alignment.Center
            ) {
                Text("🍎")
            }
        }
    }
}
