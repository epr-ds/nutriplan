package com.nutriplan.android.screen.feedback

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.semantics
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp

/**
 * Beta feedback screen — allows testers to submit bug reports and feature requests.
 * Feedback is stored locally and can be exported or submitted via the app's API endpoint.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FeedbackScreen(
    onNavigateBack: () -> Unit,
    onSubmitFeedback: (String, String, String) -> Unit = { _, _, _ -> }
) {
    var category by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var stepsToReproduce by remember { mutableStateOf("") }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Beta Feedback") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(paddingValues)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Category selector
            Text(
                text = "Category",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            FeedbackCategorySelector(
                selected = category,
                onSelected = { category = it }
            )

            // Description
            Text(
                text = "Description",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            OutlinedTextField(
                value = description,
                onValueChange = { description = it },
                placeholder = { Text("What did you experience?") },
                modifier = Modifier.fillMaxWidth(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
                minLines = 4
            )

            // Steps to reproduce (optional)
            Text(
                text = "Steps to Reproduce (optional)",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            OutlinedTextField(
                value = stepsToReproduce,
                onValueChange = { stepsToReproduce = it },
                placeholder = { Text("1. Open app\n2. Navigate to...\n3. Tap...") },
                modifier = Modifier.fillMaxWidth(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
                minLines = 3
            )

            // Submit button
            com.nutriplan.android.component.NutriPlanButton(
                text = "Submit Feedback",
                onClick = {
                    if (description.isNotBlank()) {
                        onSubmitFeedback(category, description, stepsToReproduce)
                    }
                },
                enabled = description.isNotBlank()
            )

            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

@Composable
private fun FeedbackCategorySelector(
    selected: String,
    onSelected: (String) -> Unit
) {
    val categories = listOf("Bug", "Feature Request", "Performance", "UI/UX", "Other")

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        categories.forEach { category ->
            androidx.compose.material3.Card(
                onClick = { onSelected(category) },
                modifier = Modifier.fillMaxWidth()
            ) {
                RadioButton(
                    selected = selected == category,
                    onClick = { onSelected(category) },
                    modifier = Modifier.padding(start = 12.dp, top = 12.dp, bottom = 12.dp)
                )
                Text(
                    text = category,
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier
                        .padding(start = 8.dp, end = 16.dp, top = 12.dp, bottom = 12.dp)
                        .align(Alignment.CenterVertically)
                )
            }
        }
    }
}
