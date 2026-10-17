package com.nutriplan.android.screen.profile

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
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.component.NutriPlanButton
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.screen.onboarding.AllergiesStep
import com.nutriplan.android.screen.onboarding.DietStep
import com.nutriplan.android.screen.onboarding.TargetsStep
import com.nutriplan.shared.onboarding.OnboardingAnswers
import com.nutriplan.shared.profile.ProfileViewModel
import kotlinx.coroutines.launch

/**
 * Edit dietary preferences from the profile (IDN-606).
 *
 * Reuses the onboarding step editors and maps the profile's preferences into [OnboardingAnswers],
 * so the same catalogs and macro defaults are used everywhere.
 */
@Composable
fun DietaryPreferencesScreen(
    onDone: () -> Unit,
    onBack: () -> Unit,
) {
    val viewModel = koinInject<ProfileViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    var answers by remember { mutableStateOf(OnboardingAnswers()) }
    var seeded by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        if (!state.hasProfile) viewModel.load()
    }
    LaunchedEffect(state.profile) {
        if (!seeded && state.profile != null) {
            answers = OnboardingAnswers.from(state.profile?.dietaryPreferences)
            seeded = true
        }
    }
    LaunchedEffect(state.isSaved) {
        if (state.isSaved) {
            viewModel.consumeSaved()
            onDone()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
    ) {
        Text("Dietary preferences", style = MaterialTheme.typography.headlineSmall)

        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState()),
        ) {
            DietStep(answers) { answers = it }
            Spacer(modifier = Modifier.height(24.dp))
            AllergiesStep(answers) { answers = it }
            Spacer(modifier = Modifier.height(24.dp))
            TargetsStep(answers) { answers = it }
        }

        state.saveError?.let { message ->
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = message,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.semantics { contentDescription = "Error: $message" },
            )
        }

        Spacer(modifier = Modifier.height(16.dp))

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
                onClick = { scope.launch { viewModel.savePreferences(answers.toRequest()) } },
                isLoading = state.isSaving,
                modifier = Modifier.weight(1f),
            ) {
                Text("Save")
            }
        }
    }
}
