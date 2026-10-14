package com.nutriplan.android.component

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.ui.text.input.KeyboardOptions
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.Alignment
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import com.nutriplan.android.ui.theme.NutriPlanTheme

/**
 * Primary button component for the app.
 */
@Composable
fun NutriPlanButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    isEnabled: Boolean = true,
    isLoading: Boolean = false,
    content: @Composable () -> Unit
) {
    Button(
        onClick = onClick,
        modifier = modifier,
        enabled = isEnabled && !isLoading,
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.primary,
            // F5: Raised from 0.38f to 0.48f for WCAG AA non-text contrast ≥3:1
            disabledContainerColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.48f)
        )
    ) {
        if (isLoading) {
            // F24: Add contextual accessibility label for loading spinner
            Box(modifier = Modifier.semantics { contentDescription = "Loading" }) {
                CircularProgressIndicator(
                    modifier = Modifier.size(24.dp),
                    color = MaterialTheme.colorScheme.onPrimary,
                    trackColor = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.2f)
                )
            }
            Spacer(modifier = Modifier.width(8.dp))
        }
        content()
    }
}

/**
 * Text field component for the app.
 */
@Composable
fun NutriPlanTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    placeholder: String = "",
    isPassword: Boolean = false,
    isError: Boolean = false,
    errorMessage: String = "",
    keyboardType: androidx.compose.ui.text.input.KeyboardType = androidx.compose.ui.text.input.KeyboardType.Text
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        placeholder = { Text(placeholder) },
        visualTransformation = if (isPassword) PasswordVisualTransformation() else VisualTransformation.None,
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        isError = isError,
        keyboardOptions = androidx.compose.ui.text.input.KeyboardOptions(keyboardType = keyboardType),
        singleLine = true
    )
    
    if (isError && errorMessage.isNotEmpty()) {
        // F27: Add live region semantics for error announcements (WCAG 3.3.1, 4.1.3)
        Text(
            text = errorMessage,
            color = MaterialTheme.colorScheme.error,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(start = 16.dp, top = 4.dp).semantics { liveRegion = androidx.compose.ui.semantics.LiveRegion.Assertive; contentDescription = "Error: $errorMessage" }
        )
    }
}

/**
 * Empty state component for screens with no content.
 */
@Composable
fun EmptyState(
    title: String,
    description: String,
    modifier: Modifier = Modifier,
    actionLabel: String? = null,
    onAction: (() -> Unit)? = null
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = title,
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.54f)
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = description,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.38f),
            textAlign = androidx.compose.ui.text.style.TextAlign.Center
        )
        
        actionLabel?.let { label ->
            Spacer(modifier = Modifier.height(24.dp))
            onAction?.let { action ->
                // F26: Add accessible hint for empty state action button
                TextButton(onClick = action, modifier = Modifier.semantics { contentDescription = "$label — tap to create a new meal plan" }) {
                    Text(label)
                }
            }
        }
    }
}
