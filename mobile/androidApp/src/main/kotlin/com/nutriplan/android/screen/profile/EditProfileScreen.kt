package com.nutriplan.android.screen.profile

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.component.NutriPlanButton
import com.nutriplan.android.component.NutriPlanTextField
import com.nutriplan.android.di.koinInject
import com.nutriplan.shared.profile.ProfileViewModel
import kotlinx.coroutines.launch

/**
 * Edit the display name and avatar (IDN-606). Reuses the shared [ProfileViewModel] state, so the
 * profile screen reflects the change as soon as it is saved.
 */
@Composable
fun EditProfileScreen(
    onDone: () -> Unit,
    onBack: () -> Unit,
) {
    val viewModel = koinInject<ProfileViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    var name by remember { mutableStateOf("") }
    var hasSeededName by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        if (!state.hasProfile) viewModel.load()
    }
    // Seed the field from the loaded profile exactly once.
    LaunchedEffect(state.profile) {
        if (!hasSeededName && state.profile != null) {
            name = state.profile?.name.orEmpty()
            hasSeededName = true
        }
    }
    LaunchedEffect(state.isSaved) {
        if (state.isSaved) {
            viewModel.consumeSaved()
            onDone()
        }
    }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) {
            scope.launch {
                val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                    ?: return@launch
                val contentType = context.contentResolver.getType(uri) ?: "image/jpeg"
                viewModel.updateAvatar(contentType, bytes)
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Edit profile", style = MaterialTheme.typography.headlineSmall)

        NutriPlanTextField(
            value = name,
            onValueChange = { name = it },
            label = "Name",
            placeholder = "Enter your name",
        )

        OutlinedButton(
            onClick = {
                picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
            },
            enabled = !state.isSaving,
            modifier = Modifier
                .fillMaxWidth()
                .height(48.dp),
        ) {
            Text("Change avatar")
        }

        state.saveError?.let { message ->
            Text(
                text = message,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.semantics { contentDescription = "Error: $message" },
            )
        }

        Spacer(modifier = Modifier.height(8.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            OutlinedButton(
                onClick = onBack,
                modifier = Modifier.weight(1f),
            ) {
                Text("Cancel")
            }
            NutriPlanButton(
                onClick = { scope.launch { viewModel.saveName(name) } },
                isLoading = state.isSaving,
                isEnabled = name.isNotBlank(),
                modifier = Modifier.weight(1f),
            ) {
                Text("Save")
            }
        }
    }
}
