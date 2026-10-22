@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.ai

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.error
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.android.di.koinInjectRetained
import com.nutriplan.android.i18n.analyzeMessageRes
import com.nutriplan.android.screen.recipes.formatQuantity
import com.nutriplan.shared.ai.AiError
import com.nutriplan.shared.ai.AiLoadingStage
import com.nutriplan.shared.ai.AnalyzeMealUiState
import com.nutriplan.shared.ai.AnalyzeMealViewModel
import com.nutriplan.shared.data.model.NutritionalInfo
import kotlinx.coroutines.launch

/** Test tags for the analyze-meal screen (used by the Robolectric UI tests). */
object AnalyzeMealTestTags {
    const val LIST = "analyze_meal_list"
    const val DESCRIPTION = "analyze_meal_description"
    const val SUBMIT = "analyze_meal_submit"
    const val LOADING = "analyze_meal_loading"
    const val ERROR_BANNER = "analyze_meal_error_banner"
    const val NUTRITION = "analyze_meal_nutrition"
    const val ALIGNMENT = "analyze_meal_alignment"
    const val WARNING = "analyze_meal_warning"
    const val NO_WARNINGS = "analyze_meal_no_warnings"
    const val DISCLAIMER = "analyze_meal_disclaimer"
}

/**
 * AIA-607: describe a meal in words and get its estimated nutrition, how it fits the user's targets
 * and any warnings, from the AI Advisor. [onSessionExpired] is called when the server rejects the
 * session.
 */
@Composable
fun AnalyzeMealScreen(
    onBack: () -> Unit,
    onSessionExpired: () -> Unit,
) {
    // Kept for the life of the screen, so the answer survives a trip elsewhere and back.
    val viewModel = koinInjectRetained<AnalyzeMealViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(state.error) {
        if (state.error == AiError.SESSION_EXPIRED) onSessionExpired()
    }

    AnalyzeMealScreenContent(
        state = state,
        onDescriptionChange = viewModel::onDescriptionChange,
        onAnalyze = { scope.launch { viewModel.analyze() } },
        onBack = onBack,
        loadingStage = rememberAiLoadingStage(state.isAnalyzing),
    )
}

/** Stateless analyze-meal screen: renders [state]; every action is a callback. */
@Composable
fun AnalyzeMealScreenContent(
    state: AnalyzeMealUiState,
    onDescriptionChange: (String) -> Unit,
    onAnalyze: () -> Unit,
    onBack: () -> Unit,
    /** How long the request has been running (AIA-606). */
    loadingStage: AiLoadingStage = AiLoadingStage.STARTED,
) {
    val loadingDescription = stringResource(R.string.cd_analyze_meal_loading)
    val result = state.result

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = stringResource(R.string.analyze_meal_title),
                        modifier = Modifier.semantics { heading() },
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = stringResource(R.string.cd_meal_plans_back),
                        )
                    }
                },
            )
        },
    ) { paddingValues ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .testTag(AnalyzeMealTestTags.LIST),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item(key = "form") { DescriptionForm(state, onDescriptionChange, onAnalyze) }

            state.error?.let { error ->
                item(key = "error") {
                    AiErrorCard(
                        message = stringResource(error.analyzeMessageRes()),
                        onRetry = onAnalyze,
                        messageTestTag = AnalyzeMealTestTags.ERROR_BANNER,
                        retryEnabled = !state.isAnalyzing,
                    )
                }
            }

            if (state.isAnalyzing) {
                item(key = "loading") {
                    AiLoadingSkeleton(
                        stage = loadingStage,
                        description = loadingDescription,
                        modifier = Modifier.testTag(AnalyzeMealTestTags.LOADING),
                        cards = 2,
                    )
                }
            } else if (result != null) {
                item(key = "nutrition") { NutritionCard(result.nutritionalInfo, state.analyzedDescription) }
                result.alignment?.takeIf { it.score != null || !it.details.isNullOrBlank() }?.let { alignment ->
                    item(key = "alignment") { AlignmentCard(alignment, testTag = AnalyzeMealTestTags.ALIGNMENT) }
                }
                item(key = "warnings-heading") {
                    Text(
                        text = stringResource(R.string.analyze_meal_warnings_heading),
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.semantics { heading() },
                    )
                }
                if (result.warnings.isEmpty()) {
                    item(key = "no-warnings") {
                        Text(
                            text = stringResource(R.string.analyze_meal_no_warnings),
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.testTag(AnalyzeMealTestTags.NO_WARNINGS),
                        )
                    }
                }
                items(result.warnings) { warning -> WarningRow(warning) }
                // Required with every AI answer: what is shown is not medical advice.
                item(key = "disclaimer") {
                    AiDisclaimer(
                        text = result.disclaimer?.takeIf { it.isNotBlank() }
                            ?: stringResource(R.string.analyze_meal_disclaimer_fallback),
                        testTag = AnalyzeMealTestTags.DISCLAIMER,
                    )
                }
            }
        }
    }
}

@Composable
private fun DescriptionForm(
    state: AnalyzeMealUiState,
    onDescriptionChange: (String) -> Unit,
    onAnalyze: () -> Unit,
) {
    val missing = stringResource(R.string.error_analyze_meal_description_missing)
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            text = stringResource(R.string.analyze_meal_intro),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        OutlinedTextField(
            value = state.description,
            onValueChange = onDescriptionChange,
            label = { Text(stringResource(R.string.analyze_meal_description_label)) },
            placeholder = { Text(stringResource(R.string.analyze_meal_description_hint)) },
            isError = state.descriptionMissing,
            supportingText = {
                Text(
                    if (state.descriptionMissing) {
                        missing
                    } else {
                        stringResource(
                            R.string.analyze_meal_description_count,
                            state.description.length,
                            AnalyzeMealViewModel.MAX_DESCRIPTION_LENGTH,
                        )
                    },
                )
            },
            minLines = 3,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { if (!state.isAnalyzing) onAnalyze() }),
            modifier = Modifier
                .fillMaxWidth()
                .testTag(AnalyzeMealTestTags.DESCRIPTION)
                .semantics { if (state.descriptionMissing) error(missing) },
        )
        Button(
            onClick = onAnalyze,
            enabled = !state.isAnalyzing,
            modifier = Modifier
                .fillMaxWidth()
                .testTag(AnalyzeMealTestTags.SUBMIT),
        ) {
            Text(stringResource(R.string.analyze_meal_submit))
        }
    }
}

@Composable
private fun NutritionCard(info: NutritionalInfo?, description: String?) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(AnalyzeMealTestTags.NUTRITION)
            .semantics(mergeDescendants = true) {},
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                text = stringResource(R.string.analyze_meal_nutrition_title),
                style = MaterialTheme.typography.titleSmall,
            )
            if (description != null) {
                Text(
                    text = description,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            val rows = listOfNotNull(
                info?.calories?.let {
                    stringResource(R.string.analyze_meal_calories) to stringResource(R.string.recipe_kcal, it)
                },
                info?.protein?.let { stringResource(R.string.analyze_meal_protein) to grams(it) },
                info?.carbs?.let { stringResource(R.string.analyze_meal_carbs) to grams(it) },
                info?.fat?.let { stringResource(R.string.analyze_meal_fat) to grams(it) },
                info?.sugar?.let { stringResource(R.string.analyze_meal_sugar) to grams(it) },
            )
            if (rows.isEmpty()) {
                Text(
                    text = stringResource(R.string.analyze_meal_nutrition_unknown),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            rows.forEach { (label, value) ->
                Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                    Text(text = label, style = MaterialTheme.typography.bodyMedium)
                    Text(text = value, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}

@Composable
private fun grams(value: Double): String =
    stringResource(R.string.analyze_meal_grams, formatQuantity(roundToTenth(value)))

/** One decimal at most: estimates are not more precise than that. */
private fun roundToTenth(value: Double): Double = kotlin.math.round(value * 10) / 10

@Composable
private fun WarningRow(warning: String) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
        modifier = Modifier
            .fillMaxWidth()
            .testTag(AnalyzeMealTestTags.WARNING)
            .semantics(mergeDescendants = true) {},
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                Icons.Filled.Warning,
                contentDescription = stringResource(R.string.cd_analyze_meal_warning),
                tint = MaterialTheme.colorScheme.onErrorContainer,
                modifier = Modifier.size(20.dp),
            )
            Text(
                text = warning,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onErrorContainer,
            )
        }
    }
}
