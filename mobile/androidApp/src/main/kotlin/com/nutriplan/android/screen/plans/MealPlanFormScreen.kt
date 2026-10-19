@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.plans

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.semantics.Role
import com.nutriplan.android.R
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.messageRes
import com.nutriplan.shared.planning.MealPlanFormError
import com.nutriplan.shared.planning.MealPlanFormUiState
import com.nutriplan.shared.planning.MealPlanFormViewModel
import com.nutriplan.shared.planning.PlanFieldError
import kotlinx.coroutines.launch

/** Test tags for the create-plan form (used by the Robolectric UI tests). */
object MealPlanFormTestTags {
    const val NAME = "plan_form_name"
    const val START_DATE = "plan_form_start_date"
    const val END_DATE = "plan_form_end_date"
    const val CALORIES = "plan_form_calories"
    const val SUBMIT = "plan_form_submit"
    const val ERROR_BANNER = "plan_form_error_banner"
}

/**
 * DPL-503: create a meal plan. The calorie target is prefilled from the user's dietary preferences,
 * the dates start as a week from today, and the plan is opened as soon as the server created it
 * ([onCreated]). [onSessionExpired] is called when the server rejects the session.
 */
@Composable
fun MealPlanFormScreen(
    onBack: () -> Unit,
    onCreated: (planId: String) -> Unit,
    onSessionExpired: () -> Unit,
) {
    val viewModel = koinInject<MealPlanFormViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel) { viewModel.start(todayIso()) }
    LaunchedEffect(state.createdPlanId) { state.createdPlanId?.let(onCreated) }
    LaunchedEffect(state.error) {
        if (state.error == MealPlanFormError.SESSION_EXPIRED) onSessionExpired()
    }

    MealPlanFormScreenContent(
        state = state,
        onNameChange = viewModel::onNameChange,
        onStartDateChange = viewModel::onStartDateChange,
        onEndDateChange = viewModel::onEndDateChange,
        onCaloriesChange = viewModel::onCaloriesChange,
        onSubmit = { scope.launch { viewModel.save() } },
        onBack = onBack,
    )
}

/** Stateless create-plan form: renders [state]; every action is a callback. */
@Composable
fun MealPlanFormScreenContent(
    state: MealPlanFormUiState,
    onNameChange: (String) -> Unit,
    onStartDateChange: (String) -> Unit,
    onEndDateChange: (String) -> Unit,
    onCaloriesChange: (String) -> Unit,
    onSubmit: () -> Unit,
    onBack: () -> Unit,
) {
    val savingDescription = stringResource(R.string.cd_plan_form_saving)

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = stringResource(R.string.plan_form_title),
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
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            state.error?.let { error ->
                Text(
                    text = stringResource(error.messageRes()),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier
                        .testTag(MealPlanFormTestTags.ERROR_BANNER)
                        .semantics { liveRegion = LiveRegionMode.Polite },
                )
            }

            OutlinedTextField(
                value = state.name,
                onValueChange = onNameChange,
                label = { Text(stringResource(R.string.plan_form_name_label)) },
                singleLine = true,
                isError = state.nameError != null,
                supportingText = state.nameError.supportingText(),
                keyboardOptions = KeyboardOptions(
                    capitalization = KeyboardCapitalization.Sentences,
                    imeAction = ImeAction.Next,
                ),
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag(MealPlanFormTestTags.NAME),
            )

            DateField(
                label = stringResource(R.string.plan_form_start_label),
                isoDate = state.startDate,
                error = state.startDateError,
                tag = MealPlanFormTestTags.START_DATE,
                onPicked = onStartDateChange,
            )

            DateField(
                label = stringResource(R.string.plan_form_end_label),
                isoDate = state.endDate,
                error = state.endDateError,
                tag = MealPlanFormTestTags.END_DATE,
                onPicked = onEndDateChange,
            )

            OutlinedTextField(
                value = state.calories,
                onValueChange = onCaloriesChange,
                label = { Text(stringResource(R.string.plan_form_calories_label)) },
                suffix = { Text(stringResource(R.string.plan_form_calories_suffix)) },
                singleLine = true,
                isError = state.caloriesError != null,
                supportingText = when {
                    state.caloriesError != null -> state.caloriesError.supportingText()
                    state.caloriesPrefilled -> ({ Text(stringResource(R.string.plan_form_calories_prefilled)) })
                    else -> null
                },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag(MealPlanFormTestTags.CALORIES),
            )

            Button(
                onClick = onSubmit,
                enabled = !state.isSaving,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 48.dp)
                    .testTag(MealPlanFormTestTags.SUBMIT),
            ) {
                if (state.isSaving) {
                    CircularProgressIndicator(
                        modifier = Modifier
                            .size(20.dp)
                            .semantics { contentDescription = savingDescription },
                        strokeWidth = 2.dp,
                    )
                } else {
                    Text(stringResource(R.string.plan_form_submit))
                }
            }
        }
    }
}

/** The inline error text of a field, or null when it has none. */
private fun PlanFieldError?.supportingText(): (@Composable () -> Unit)? =
    this?.let { error -> { Text(stringResource(error.messageRes())) } }

/**
 * A read-only field showing a date that opens Material's date picker when tapped. (A read-only
 * text field swallows taps, so a transparent button sits over it.)
 */
@Composable
private fun DateField(
    label: String,
    isoDate: String,
    error: PlanFieldError?,
    tag: String,
    onPicked: (String) -> Unit,
) {
    var showPicker by remember { mutableStateOf(false) }

    Box(modifier = Modifier.fillMaxWidth()) {
        OutlinedTextField(
            value = if (isoDate.isBlank()) "" else formatPlanDay(isoDate),
            onValueChange = {},
            readOnly = true,
            label = { Text(label) },
            trailingIcon = { Icon(Icons.Default.CalendarMonth, contentDescription = null) },
            isError = error != null,
            supportingText = error.supportingText(),
            modifier = Modifier
                .fillMaxWidth()
                .testTag(tag),
        )
        Box(
            modifier = Modifier
                .matchParentSize()
                .clickable(role = Role.Button, onClickLabel = label) { showPicker = true },
        )
    }

    if (showPicker) {
        val pickerState = rememberDatePickerState(initialSelectedDateMillis = isoToPickerMillis(isoDate))
        DatePickerDialog(
            onDismissRequest = { showPicker = false },
            confirmButton = {
                TextButton(
                    onClick = {
                        pickerState.selectedDateMillis?.let { onPicked(pickerMillisToIso(it)) }
                        showPicker = false
                    },
                ) { Text(stringResource(android.R.string.ok)) }
            },
            dismissButton = {
                TextButton(onClick = { showPicker = false }) { Text(stringResource(android.R.string.cancel)) }
            },
        ) {
            DatePicker(state = pickerState)
        }
    }
}
