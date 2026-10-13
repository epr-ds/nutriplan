package com.nutriplan.android.screen.auth

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.background
import androidx.compose.material3.*
import androidx.compose.foundation.background
import androidx.compose.runtime.*
import androidx.compose.foundation.background
import androidx.compose.ui.Alignment
import androidx.compose.foundation.background
import androidx.compose.ui.Modifier
import androidx.compose.foundation.background
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.background
import com.nutriplan.android.component.NutriPlanButton
import androidx.compose.foundation.background
import com.nutriplan.android.component.NutriPlanTextField
import androidx.compose.foundation.background
import com.nutriplan.android.di.koinInject
import androidx.compose.foundation.background

@Composable
fun LoginScreen(
    onLoginSuccess: () -> Unit,
    onNavigateToRegister: () -> Unit,
    onNavigateToForgotPassword: () -> Unit
) {
    val authRepository = koinInject<com.nutriplan.shared.data.repository.AuthRepository>()
    
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
            placeholder = "Enter your email"
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
            Text(
                text = it,
                color = MaterialTheme.colorScheme.error
            )
        }
        
        Spacer(modifier = Modifier.height(24.dp))
        
        NutriPlanButton(
            onClick = {
                isLoading = true
                errorMessage = null
                // TODO: Implement login logic
                // authRepository.login(email, password)
                isLoading = false
                onLoginSuccess()
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
            Box(
                modifier = Modifier
                    .weight(1f)
                    .aspectRatio(1f)
                    .background(
                        MaterialTheme.colorScheme.surfaceVariant,
                        MaterialTheme.shapes.medium
                    ),
                contentAlignment = Alignment.Center
            ) {
                Text("G")
            }
            Box(
                modifier = Modifier
                    .weight(1f)
                    .aspectRatio(1f)
                    .background(
                        MaterialTheme.colorScheme.surfaceVariant,
                        MaterialTheme.shapes.medium
                    ),
                contentAlignment = Alignment.Center
            ) {
                Text("ðŸŽ")
            }
        }
    }
}
