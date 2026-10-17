package com.nutriplan.android.screen.onboarding

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.component.NutriPlanButton
import com.nutriplan.android.di.koinInject
import com.nutriplan.shared.onboarding.MacroCalculator
import com.nutriplan.shared.onboarding.OnboardingAnswers
import com.nutriplan.shared.onboarding.OnboardingContent
import com.nutriplan.shared.onboarding.OnboardingOption
import com.nutriplan.shared.onboarding.OnboardingStep
import com.nutriplan.shared.onboarding.OnboardingUiState
import com.nutriplan.shared.onboarding.OnboardingViewModel
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

/**
 * Post-signup onboarding wizard (IDN-602/603/604).
 *
 * A thin rendering layer over the shared [OnboardingViewModel]: it shows the current step, a
 * progress bar, back/skip/next, and finishes by persisting the answers and flipping the session.
 */
@Composable
fun OnboardingWizardScreen(
    onComplete: () -> Unit,
) {
    val viewModel = koinInject<OnboardingViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(state.isComplete) {
        if (state.isComplete) onComplete()
    }

    // Seed the calorie/macro defaults the first time the targets step is shown.
    LaunchedEffect(state.step) {
        if (state.step == OnboardingStep.TARGETS && state.answers.dailyCalorieTarget == null) {
            viewModel.updateAnswers(
                state.answers.copy(
                    dailyCalorieTarget = MacroCalculator.DEFAULT_CALORIES,
                    macroTargets = MacroCalculator.defaultMacroTargets(MacroCalculator.DEFAULT_CALORIES),
                ),
            )
        }
    }

    OnboardingWizardContent(
        state = state,
        onUpdateAnswers = viewModel::updateAnswers,
        onBack = viewModel::back,
        onNext = viewModel::next,
        onSkip = { scope.launch { viewModel.finish() } },
        onFinish = { scope.launch { viewModel.finish() } },
    )
}

/**
 * Stateless onboarding wizard UI (IDN-602/603/604/705). Kept separate from
 * [OnboardingWizardScreen] so the accessibility checks can render it directly without the DI graph.
 */
@Composable
internal fun OnboardingWizardContent(
    state: OnboardingUiState,
    onUpdateAnswers: (OnboardingAnswers) -> Unit,
    onBack: () -> Unit,
    onNext: () -> Unit,
    onSkip: () -> Unit,
    onFinish: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "Step ${state.stepNumber} of ${state.stepCount}",
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = onSkip) {
                Text("Skip")
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        LinearProgressIndicator(
            progress = { state.progress },
            modifier = Modifier
                .fillMaxWidth()
                .semantics { contentDescription = "Progress: step ${state.stepNumber} of ${state.stepCount}" },
        )

        Spacer(modifier = Modifier.height(24.dp))

        Box(modifier = Modifier.weight(1f)) {
            Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                when (state.step) {
                    OnboardingStep.DIET -> DietStep(state.answers, onUpdateAnswers)
                    OnboardingStep.ALLERGIES -> AllergiesStep(state.answers, onUpdateAnswers)
                    OnboardingStep.TARGETS -> TargetsStep(state.answers, onUpdateAnswers)
                }
            }
        }

        state.error?.let { message ->
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = message,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            )
        }

        Spacer(modifier = Modifier.height(16.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (!state.isFirstStep) {
                OutlinedButton(onClick = onBack) {
                    Text("Back")
                }
                Spacer(modifier = Modifier.width(16.dp))
            }
            NutriPlanButton(
                onClick = { if (state.isLastStep) onFinish() else onNext() },
                isLoading = state.isSaving,
                modifier = Modifier.weight(1f),
            ) {
                Text(if (state.isLastStep) "Finish" else "Next")
            }
        }
    }
}

@Composable
internal fun DietStep(answers: OnboardingAnswers, onChange: (OnboardingAnswers) -> Unit) {
    Column {
        Text(
            "What's your diet?",
            style = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.semantics { heading() },
        )
        Spacer(modifier = Modifier.height(8.dp))

        OnboardingContent.dietTypes.forEach { option ->
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .semantics { contentDescription = option.label() },
            ) {
                RadioButton(
                    selected = answers.dietType == option.value,
                    onClick = { onChange(answers.copy(dietType = option.value)) },
                )
                Text(option.label())
            }
        }

        Spacer(modifier = Modifier.height(24.dp))
        Text("Favourite cuisines", style = MaterialTheme.typography.titleLarge)
        Spacer(modifier = Modifier.height(8.dp))
        OptionChips(
            options = OnboardingContent.cuisines,
            selected = answers.cuisinePreferences,
            onToggle = { value ->
                onChange(answers.copy(cuisinePreferences = answers.cuisinePreferences.toggle(value)))
            },
        )
    }
}

@Composable
internal fun AllergiesStep(answers: OnboardingAnswers, onChange: (OnboardingAnswers) -> Unit) {
    Column {
        Text(
            "Any allergies?",
            style = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.semantics { heading() },
        )
        Spacer(modifier = Modifier.height(8.dp))
        OptionChips(
            options = OnboardingContent.commonAllergens,
            selected = answers.allergies,
            onToggle = { value -> onChange(answers.copy(allergies = answers.allergies.toggle(value))) },
        )

        Spacer(modifier = Modifier.height(24.dp))
        Text("Ingredients to avoid", style = MaterialTheme.typography.titleLarge)
        Spacer(modifier = Modifier.height(8.dp))
        OptionChips(
            options = OnboardingContent.commonExcludedIngredients,
            selected = answers.excludedIngredients,
            onToggle = { value ->
                onChange(answers.copy(excludedIngredients = answers.excludedIngredients.toggle(value)))
            },
        )
    }
}

@Composable
internal fun TargetsStep(answers: OnboardingAnswers, onChange: (OnboardingAnswers) -> Unit) {
    val calories = answers.dailyCalorieTarget ?: MacroCalculator.DEFAULT_CALORIES
    val macros = answers.macroTargets ?: MacroCalculator.defaultMacroTargets(calories)

    Column {
        Text(
            "Daily calorie target",
            style = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.semantics { heading() },
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = "$calories kcal",
            style = MaterialTheme.typography.titleLarge,
            modifier = Modifier.semantics { contentDescription = "Calorie target: $calories kilocalories" },
        )
        Slider(
            value = calories.toFloat(),
            onValueChange = { value ->
                val rounded = value.roundToInt()
                onChange(
                    answers.copy(
                        dailyCalorieTarget = rounded,
                        macroTargets = MacroCalculator.defaultMacroTargets(rounded),
                    ),
                )
            },
            valueRange = MacroCalculator.MIN_CALORIES.toFloat()..MacroCalculator.MAX_CALORIES.toFloat(),
        )

        Spacer(modifier = Modifier.height(16.dp))
        Text("Suggested macros", style = MaterialTheme.typography.titleLarge)
        Spacer(modifier = Modifier.height(8.dp))
        Text("Protein ${macros.proteinGrams} g · Carbs ${macros.carbsGrams} g · Fat ${macros.fatGrams} g")

        Spacer(modifier = Modifier.height(24.dp))
        Text("How satisfying are your current meals?", style = MaterialTheme.typography.titleLarge)
        Spacer(modifier = Modifier.height(8.dp))
        OptionChips(
            options = (1..5).map { OnboardingOption(it.toString(), it.toString(), it.toString()) },
            selected = listOfNotNull(answers.appetiteSatisfactionLevel?.toString()),
            onToggle = { value ->
                onChange(answers.copy(appetiteSatisfactionLevel = value.toIntOrNull()))
            },
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun OptionChips(
    options: List<OnboardingOption>,
    selected: List<String>,
    onToggle: (String) -> Unit,
) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        options.forEach { option ->
            FilterChip(
                selected = option.value in selected,
                onClick = { onToggle(option.value) },
                label = { Text(option.label()) },
            )
        }
    }
}

private fun List<String>.toggle(value: String): List<String> =
    if (value in this) this - value else this + value

/** Bilingual label: Spanish on an `es` device, English otherwise (IDN-903). */
private fun OnboardingOption.label(): String =
    if (java.util.Locale.getDefault().language == "es") labelEs else labelEn
