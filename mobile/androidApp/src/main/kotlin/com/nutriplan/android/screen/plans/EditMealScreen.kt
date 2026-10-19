@file:OptIn(
    androidx.compose.material3.ExperimentalMaterial3Api::class,
    androidx.compose.foundation.layout.ExperimentalLayoutApi::class,
)

package com.nutriplan.android.screen.plans

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.mealTypeLabelRes
import com.nutriplan.android.i18n.messageRes
import com.nutriplan.shared.planning.EditMealError
import com.nutriplan.shared.planning.EditMealUiState
import com.nutriplan.shared.planning.EditMealViewModel
import kotlinx.coroutines.launch

/** Test tags for the edit-meal screen (used by the Robolectric UI tests). */
object EditMealTestTags {
    const val LOADING = "edit_meal_loading"
    const val SERVINGS = "edit_meal_servings"
    const val DAY = "edit_meal_day"
    const val SATISFACTION = "edit_meal_satisfaction"
    const val SAVE = "edit_meal_save"
    const val REMOVE = "edit_meal_remove"
    const val CONFIRM_REMOVE = "edit_meal_confirm_remove"
    const val ERROR_BANNER = "edit_meal_error_banner"
}

/**
 * Edit a planned meal: change its servings or day, rate how satisfying it was (1 to 5), or remove
 * it from the plan (DPL-508). [onDone] is called after a save or a removal (or when nothing changed);
 * [onSessionExpired] when the server rejects the session.
 */
@Composable
fun EditMealScreen(
    planId: String,
    mealId: String,
    onBack: () -> Unit,
    onDone: () -> Unit,
    onSessionExpired: () -> Unit,
) {
    val viewModel = koinInject<EditMealViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel, planId, mealId) { viewModel.start(planId, mealId) }
    LaunchedEffect(state.isDone) { if (state.isDone) onDone() }
    LaunchedEffect(state.error, state.loadError) {
        if (state.error == EditMealError.SESSION_EXPIRED || state.loadError == EditMealError.SESSION_EXPIRED) {
            onSessionExpired()
        }
    }

    EditMealScreenContent(
        state = state,
        onServingsChange = viewModel::onServingsChange,
        onDayChange = viewModel::onDayChange,
        onSatisfactionChange = viewModel::onSatisfactionChange,
        onSave = { scope.launch { viewModel.save() } },
        onRemove = { scope.launch { viewModel.remove() } },
        onRetryLoad = { scope.launch { viewModel.start(planId, mealId) } },
        onBack = onBack,
    )
}

/** Stateless edit-meal form: renders [state]; every action is a callback. */
@Composable
fun EditMealScreenContent(
    state: EditMealUiState,
    onServingsChange: (String) -> Unit,
    onDayChange: (Int?) -> Unit,
    onSatisfactionChange: (Int) -> Unit,
    onSave: () -> Unit,
    onRemove: () -> Unit,
    onRetryLoad: () -> Unit,
    onBack: () -> Unit,
) {
    val meal = state.meal
    val loadError = state.loadError
    val loadingDescription = stringResource(R.string.cd_edit_meal_loading)
    val busyDescription = stringResource(R.string.cd_edit_meal_saving)
    var confirmRemove by remember { mutableStateOf(false) }
    val busy = state.isSaving || state.isRemoving

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = stringResource(R.string.edit_meal_title),
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
        val content = Modifier
            .fillMaxSize()
            .padding(paddingValues)

        when {
            meal != null -> Column(
                modifier = content
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Column(modifier = Modifier.semantics(mergeDescendants = true) {}) {
                    Text(
                        text = mealTypeLabelRes(meal.mealType)?.let { stringResource(it) } ?: meal.mealType,
                        style = MaterialTheme.typography.titleLarge,
                    )
                    meal.nutritionalInfo?.calories?.let {
                        Text(
                            text = stringResource(R.string.plan_detail_meal_calories, it),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }

                state.error?.let { error ->
                    Text(
                        text = stringResource(error.messageRes()),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier
                            .testTag(EditMealTestTags.ERROR_BANNER)
                            .semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }

                OutlinedTextField(
                    value = state.servings,
                    onValueChange = onServingsChange,
                    enabled = !busy,
                    label = { Text(stringResource(R.string.add_meal_servings_label)) },
                    singleLine = true,
                    isError = state.servingsError != null,
                    supportingText = state.servingsError?.let { error -> { Text(stringResource(error.messageRes())) } },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal, imeAction = ImeAction.Done),
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag(EditMealTestTags.SERVINGS),
                )

                if (state.days.isNotEmpty()) {
                    DayChoice(
                        days = state.days,
                        selected = state.dayIndex,
                        onDayChange = onDayChange,
                        testTag = EditMealTestTags.DAY,
                        allowNone = state.canClearDay,
                    )
                }

                SatisfactionChoice(selected = state.satisfaction, enabled = !busy, onChange = onSatisfactionChange)

                Button(
                    onClick = onSave,
                    enabled = !busy,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 48.dp)
                        .testTag(EditMealTestTags.SAVE),
                ) {
                    if (state.isSaving) {
                        CircularProgressIndicator(
                            modifier = Modifier
                                .size(20.dp)
                                .semantics { contentDescription = busyDescription },
                            strokeWidth = 2.dp,
                        )
                    } else {
                        Text(stringResource(R.string.edit_meal_save))
                    }
                }

                OutlinedButton(
                    onClick = { confirmRemove = true },
                    enabled = !busy,
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error),
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 48.dp)
                        .testTag(EditMealTestTags.REMOVE),
                ) {
                    if (state.isRemoving) {
                        CircularProgressIndicator(
                            modifier = Modifier
                                .size(20.dp)
                                .semantics { contentDescription = busyDescription },
                            strokeWidth = 2.dp,
                        )
                    } else {
                        Text(stringResource(R.string.edit_meal_remove))
                    }
                }
            }

            state.isLoading -> Box(
                modifier = content.testTag(EditMealTestTags.LOADING),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator(
                    modifier = Modifier.semantics { contentDescription = loadingDescription },
                )
            }

            loadError != null -> ErrorState(
                message = stringResource(loadError.messageRes()),
                // A meal that no longer exists cannot be retried: the action goes back instead.
                onRetry = if (loadError == EditMealError.NOT_FOUND) onBack else onRetryLoad,
                modifier = content,
                actionLabel = stringResource(
                    if (loadError == EditMealError.NOT_FOUND) R.string.add_meal_back else R.string.meal_plans_retry,
                ),
            )
        }
    }

    if (confirmRemove) {
        AlertDialog(
            onDismissRequest = { confirmRemove = false },
            title = { Text(stringResource(R.string.edit_meal_remove_title)) },
            text = { Text(stringResource(R.string.edit_meal_remove_message)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmRemove = false
                        onRemove()
                    },
                    modifier = Modifier.testTag(EditMealTestTags.CONFIRM_REMOVE),
                ) { Text(stringResource(R.string.edit_meal_remove_confirm)) }
            },
            dismissButton = {
                TextButton(onClick = { confirmRemove = false }) { Text(stringResource(R.string.edit_meal_cancel)) }
            },
        )
    }
}

/** A 1 to 5 rating: five chips, the chosen one selected. The API can set a rating but not clear it. */
@Composable
private fun SatisfactionChoice(selected: Int?, enabled: Boolean, onChange: (Int) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            text = stringResource(R.string.edit_meal_satisfaction_label),
            style = MaterialTheme.typography.labelLarge,
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            (EditMealViewModel.MIN_SATISFACTION..EditMealViewModel.MAX_SATISFACTION).forEach { level ->
                val isSelected = selected == level
                val description = stringResource(R.string.edit_meal_satisfaction_value, level)
                FilterChip(
                    selected = isSelected,
                    onClick = { onChange(level) },
                    enabled = enabled,
                    label = { Text(level.toString()) },
                    modifier = Modifier
                        .testTag(EditMealTestTags.SATISFACTION)
                        .semantics {
                            this.selected = isSelected
                            contentDescription = description
                        },
                )
            }
        }
        if (selected == null) {
            Text(
                text = stringResource(R.string.edit_meal_satisfaction_unrated),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
