@file:OptIn(
    androidx.compose.material3.ExperimentalMaterial3Api::class,
    androidx.compose.foundation.layout.ExperimentalLayoutApi::class,
)

package com.nutriplan.android.screen.plans

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
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
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.nutriplan.android.R
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.mealTypeLabelRes
import com.nutriplan.android.i18n.messageRes
import com.nutriplan.shared.planning.AddMealDay
import com.nutriplan.shared.planning.AddMealError
import com.nutriplan.shared.planning.AddMealUiState
import com.nutriplan.shared.planning.AddMealViewModel
import kotlinx.coroutines.launch

/** Test tags for the add-meal screen (used by the Robolectric UI tests). */
object AddMealTestTags {
    const val LOADING = "add_meal_loading"
    const val RECIPE = "add_meal_recipe"
    const val MEAL_TYPE_CHIP = "add_meal_type_chip"
    const val SERVINGS = "add_meal_servings"
    const val DAY = "add_meal_day"
    const val SUBMIT = "add_meal_submit"
    const val RETRY_DAY = "add_meal_retry_day"
    const val SKIP_DAY = "add_meal_skip_day"
    const val ERROR_BANNER = "add_meal_error_banner"
}

/**
 * DPL-507: add [recipeId] to the plan [planId] as a meal: choose the meal type, the servings and
 * (optionally) the day. [onDone] is called once the meal is in the plan; [onSessionExpired] when the
 * server rejects the session.
 */
@Composable
fun AddMealScreen(
    planId: String,
    recipeId: String,
    onBack: () -> Unit,
    onDone: () -> Unit,
    onSessionExpired: () -> Unit,
) {
    val viewModel = koinInject<AddMealViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel, planId, recipeId) { viewModel.start(planId, recipeId) }
    LaunchedEffect(state.isDone) { if (state.isDone) onDone() }
    LaunchedEffect(state.error, state.loadError) {
        if (state.error == AddMealError.SESSION_EXPIRED || state.loadError == AddMealError.SESSION_EXPIRED) {
            onSessionExpired()
        }
    }

    AddMealScreenContent(
        state = state,
        onMealTypeChange = viewModel::onMealTypeChange,
        onServingsChange = viewModel::onServingsChange,
        onDayChange = viewModel::onDayChange,
        onSubmit = { scope.launch { viewModel.save() } },
        onRetryLoad = { scope.launch { viewModel.start(planId, recipeId) } },
        onSkipDay = onDone,
        onBack = onBack,
    )
}

/** Stateless add-meal form: renders [state]; every action is a callback. */
@Composable
fun AddMealScreenContent(
    state: AddMealUiState,
    onMealTypeChange: (String) -> Unit,
    onServingsChange: (String) -> Unit,
    onDayChange: (Int?) -> Unit,
    onSubmit: () -> Unit,
    onRetryLoad: () -> Unit,
    onSkipDay: () -> Unit,
    onBack: () -> Unit,
) {
    val recipe = state.recipe
    val loadError = state.loadError
    val loadingDescription = stringResource(R.string.cd_add_meal_loading)
    val savingDescription = stringResource(R.string.cd_add_meal_saving)

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = stringResource(R.string.add_meal_title),
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
            recipe != null -> Column(
                modifier = content
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                RecipeHeader(name = recipe.name, imageUrl = recipe.imageUrl, calories = recipe.nutritionalInfo?.calories)

                state.error?.let { error ->
                    Text(
                        text = stringResource(
                            if (state.dayNotSet) R.string.error_add_meal_day_not_set else error.messageRes(),
                        ),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier
                            .testTag(AddMealTestTags.ERROR_BANNER)
                            .semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }

                MealTypeChoice(state = state, onMealTypeChange = onMealTypeChange)

                OutlinedTextField(
                    value = state.servings,
                    onValueChange = onServingsChange,
                    enabled = state.addedMealId == null,
                    label = { Text(stringResource(R.string.add_meal_servings_label)) },
                    singleLine = true,
                    isError = state.servingsError != null,
                    supportingText = state.servingsError?.let { error -> { Text(stringResource(error.messageRes())) } },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal, imeAction = ImeAction.Done),
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag(AddMealTestTags.SERVINGS),
                )

                if (state.days.isNotEmpty()) {
                    DayChoice(days = state.days, selected = state.dayIndex, onDayChange = onDayChange)
                }

                Button(
                    onClick = onSubmit,
                    enabled = !state.isSaving,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 48.dp)
                        .testTag(if (state.dayNotSet) AddMealTestTags.RETRY_DAY else AddMealTestTags.SUBMIT),
                ) {
                    if (state.isSaving) {
                        CircularProgressIndicator(
                            modifier = Modifier
                                .size(20.dp)
                                .semantics { contentDescription = savingDescription },
                            strokeWidth = 2.dp,
                        )
                    } else {
                        Text(stringResource(if (state.dayNotSet) R.string.add_meal_retry_day else R.string.add_meal_submit))
                    }
                }

                if (state.dayNotSet) {
                    OutlinedButton(
                        onClick = onSkipDay,
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(min = 48.dp)
                            .testTag(AddMealTestTags.SKIP_DAY),
                    ) {
                        Text(stringResource(R.string.add_meal_skip_day))
                    }
                }
            }

            state.isLoading -> Box(
                modifier = content.testTag(AddMealTestTags.LOADING),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator(
                    modifier = Modifier.semantics { contentDescription = loadingDescription },
                )
            }

            loadError != null -> ErrorState(
                message = stringResource(loadError.messageRes()),
                // A recipe or plan that no longer exists cannot be retried: the action goes back instead.
                onRetry = if (loadError == AddMealError.NOT_FOUND) onBack else onRetryLoad,
                modifier = content,
                actionLabel = stringResource(
                    if (loadError == AddMealError.NOT_FOUND) R.string.add_meal_back else R.string.meal_plans_retry,
                ),
            )
        }
    }
}

@Composable
private fun RecipeHeader(name: String, imageUrl: String?, calories: Int?) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(AddMealTestTags.RECIPE)
            .semantics(mergeDescendants = true) {},
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (!imageUrl.isNullOrBlank()) {
                // Decorative: the name next to it says what the dish is.
                AsyncImage(
                    model = imageUrl,
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .size(56.dp)
                        .clip(MaterialTheme.shapes.medium),
                )
            }
            Column {
                Text(text = name, style = MaterialTheme.typography.titleMedium)
                calories?.let {
                    Text(
                        text = stringResource(R.string.add_meal_recipe_calories, it),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun MealTypeChoice(state: AddMealUiState, onMealTypeChange: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            text = stringResource(R.string.add_meal_type_label),
            style = MaterialTheme.typography.labelLarge,
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            AddMealViewModel.MEAL_TYPES.forEach { type ->
                val isSelected = state.mealType == type
                FilterChip(
                    selected = isSelected,
                    onClick = { onMealTypeChange(type) },
                    enabled = state.addedMealId == null,
                    label = { Text(mealTypeLabelRes(type)?.let { stringResource(it) } ?: type) },
                    modifier = Modifier
                        .testTag(AddMealTestTags.MEAL_TYPE_CHIP)
                        .semantics { selected = isSelected },
                )
            }
        }
        state.mealTypeError?.let { error ->
            Text(
                text = stringResource(error.messageRes()),
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            )
        }
    }
}

/**
 * The day of the plan, from a menu. (A read-only text field swallows taps, so a transparent
 * clickable area sits over it.)
 */
@Composable
private fun DayChoice(days: List<AddMealDay>, selected: Int?, onDayChange: (Int?) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val none = stringResource(R.string.add_meal_day_none)
    val selectedLabel = days.firstOrNull { it.dayIndex == selected }?.let { dayLabel(it) } ?: none

    Box(modifier = Modifier.fillMaxWidth()) {
        OutlinedTextField(
            value = selectedLabel,
            onValueChange = {},
            readOnly = true,
            label = { Text(stringResource(R.string.add_meal_day_label)) },
            trailingIcon = { Icon(Icons.Default.ArrowDropDown, contentDescription = null) },
            modifier = Modifier
                .fillMaxWidth()
                .testTag(AddMealTestTags.DAY),
        )
        Box(
            modifier = Modifier
                .matchParentSize()
                .clickable(role = Role.DropdownList) { expanded = true }
                .semantics { contentDescription = selectedLabel },
        )
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            DropdownMenuItem(
                text = { Text(none) },
                onClick = {
                    expanded = false
                    onDayChange(null)
                },
            )
            days.forEach { day ->
                DropdownMenuItem(
                    text = { Text(dayLabel(day)) },
                    onClick = {
                        expanded = false
                        onDayChange(day.dayIndex)
                    },
                )
            }
        }
    }
}

@Composable
private fun dayLabel(day: AddMealDay): String =
    "${stringResource(R.string.plan_detail_day_title, day.dayIndex + 1)} · ${formatPlanDay(day.date)}"
