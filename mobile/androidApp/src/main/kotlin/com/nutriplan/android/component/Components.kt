package com.nutriplan.android.component

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.height
import androidx.compose.ui.Alignment
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.foundation.focusable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.error
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
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
        modifier = modifier
            // F21: visible focus indicator for keyboard/switch users (WCAG 2.4.7)
            .semantics {
                role = Role.Button
                contentDescription = "Button"
            }
            .focusable(),
        enabled = isEnabled && !isLoading,
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.primary,
            // F5: Raised from 0.38f to 0.48f for WCAG AA non-text contrast ≥3:1
            // Updated to 0.6 to meet 3:1 on light backgrounds (0.48 = ~2.6:1 fails)
            disabledContainerColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.6f)
        )
    ) {
        if (isLoading) {
            // F24: Add contextual accessibility label for loading spinner
            val loadingLabel = stringResource(R.string.cd_loading)
            Box(modifier = Modifier.semantics { contentDescription = loadingLabel }) {
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
    errorMessage: String = ""
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        placeholder = { Text(placeholder) },
        visualTransformation = if (isPassword) PasswordVisualTransformation() else VisualTransformation.None,
        modifier = modifier
            .semantics {
                // F21: the field must be reachable by keyboard/switch users (WCAG 2.4.7).
                role = Role.Button
                if (isError && errorMessage.isNotEmpty()) this.error(errorMessage)
            }
            .focusable()
            .fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        isError = isError,
        singleLine = true
    )
    
    if (isError && errorMessage.isNotEmpty()) {
        // F27: live region so the error is announced when it appears (WCAG 3.3.1, 4.1.3)
        Text(
            text = errorMessage,
            color = MaterialTheme.colorScheme.error,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier
                .padding(start = 16.dp, top = 4.dp)
                .semantics { liveRegion = LiveRegionMode.Polite }
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
            color = MaterialTheme.colorScheme.onSurface
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = description,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
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

/**
 * Error state component for screens with a recoverable error.
 *
 * Provides a consistent error display with a retry action across all screens.
 */
@Composable
fun ErrorState(
    message: String,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
    actionLabel: String = "Retry"
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "⚠️",
            style = MaterialTheme.typography.displaySmall,
            color = MaterialTheme.colorScheme.error
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = "Something went wrong",
            style = MaterialTheme.typography.titleLarge,
            color = MaterialTheme.colorScheme.onSurface
        )
        
        Spacer(modifier = Modifier.height(8.dp))
        
        Text(
            text = message,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            // NTF-606: the error is a live region so screen readers announce it when it appears.
            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
        )
        
        Spacer(modifier = Modifier.height(24.dp))
        
        TextButton(
            onClick = onRetry,
            modifier = Modifier.semantics { contentDescription = "$actionLabel — tap to retry" }
        ) {
            Text(actionLabel)
        }
    }
}
