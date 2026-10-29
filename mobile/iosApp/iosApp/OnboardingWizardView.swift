import SwiftUI
import Shared
import Foundation

/// The post-signup onboarding wizard (IDN-902/903): diet + cuisines, allergies, then the daily
/// calorie target and macro split. Backed by the shared `OnboardingViewModel` -- the same one the
/// Compose wizard uses -- so both platforms render one behaviour.
///
/// The screen reads the view model's current state through `currentState()` after each mutation and
/// keeps it in `@State`, which is what makes SwiftUI re-render on next / back / answer / save.
struct OnboardingWizardView: View {
    @StateObject private var viewModel = createOnboardingViewModel()
    @State private var state: OnboardingUiState?

    /// Called when the wizard finished and the session flipped to signed in.
    let onComplete: () -> Void

    init(onComplete: (() -> Void)? = nil) {
        self.onComplete = onComplete
    }

    var body: some View {
        Group {
            if let state = state {
                wizardContent(state: state)
            }
        }
        .task { await load() }
    }

    // MARK: - state

    func load() async {
        state = viewModel.currentState()
    }

    // MARK: - actions

    private func next() {
        viewModel.next()
        state = viewModel.currentState()
    }

    private func back() {
        viewModel.back()
        state = viewModel.currentState()
    }

    private func skip() {
        Task { _ = await viewModel.finish() }
    }

    private func finish() {
        Task {
            _ = await viewModel.finish()
            state = viewModel.currentState()
            if state?.isComplete == true {
                onComplete()
            }
        }
    }

    private func update(_ answers: OnboardingAnswers) {
        viewModel.updateAnswers(answers)
        state = viewModel.currentState()
    }

    // MARK: - views

    @ViewBuilder
    private func wizardContent(state: OnboardingUiState) -> some View {
        VStack(spacing: 12) {
            HStack {
                Text("\(state.stepNumber) of \(state.stepCount)")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                Spacer()
                Button("Skip") { skip() }
            }

            ProgressView(value: state.progress)

            if let error = state.error {
                Text(errorText(error))
                    .font(.subheadline)
                    .foregroundColor(.error)
                    .accessibilityLiveRegion(.polite)
            }

            stepBody(state: state)

            Spacer(minLength: 8)

            HStack {
                if !state.isFirstStep {
                    Button("Back") { back() }
                    Spacer(minLength: 12)
                }
                Button {
                    if state.isLastStep {
                        finish()
                    } else {
                        next()
                    }
                } label: {
                    Text(state.isLastStep ? "Finish" : "Next")
                }
                .disabled(state.isSaving)
            }
        }
    }

    @ViewBuilder
    private func stepBody(state: OnboardingUiState) -> some View {
        if state.step == OnboardingStep.DIET {
            dietStep(state: state)
        } else if state.step == OnboardingStep.ALLERGIES {
            allergiesStep(state: state)
        } else {
            targetsStep(state: state)
        }
    }

    private func dietStep(state: OnboardingUiState) -> some View {
        var answers = state.answers
        return VStack(alignment: .leading, spacing: 8) {
            Text("Diet")
                .font(.headline)
                .accessibilityAddTraits(.isHeader)
            Text("What best describes your diet?")
                .font(.subheadline)
                .foregroundColor(.secondary)

            ForEach(dietOptions.indices, id: \.self) { index in
                let option = dietOptions[index]
                Button {
                    answers.dietType = option.value
                    update(answers)
                } label: {
                    HStack {
                        Text(option.label)
                            .font(.subheadline)
                            .fontWeight(state.answers.dietType == option.value ? .semibold : .regular)
                        Spacer()
                        if state.answers.dietType == option.value {
                            Image(systemName: "checkmark")
                                .foregroundColor(.accentColor)
                        }
                    }
                }
            }

            Text("Cuisines")
                .font(.subheadline)
                .fontWeight(.semibold)

            VStack(spacing: 8) {
                ForEach(cuisineOptions.indices, id: \.self) { index in
                    let option = cuisineOptions[index]
                    Button {
                        if answers.cuisinePreferences.contains(option.value) {
                            answers.cuisinePreferences.removeAll { $0 == option.value }
                        } else {
                            answers.cuisinePreferences.append(option.value)
                        }
                        update(answers)
                    } label: {
                        Text(option.label)
                            .font(.subheadline)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(
                                answers.cuisinePreferences.contains(option.value) ? Color.accentColor.opacity(0.25) : Color.secondary.opacity(0.15)
                            )
                    }
                }
            }
        }
    }

    private func allergiesStep(state: OnboardingUiState) -> some View {
        var answers = state.answers
        return VStack(alignment: .leading, spacing: 8) {
            Text("Allergies")
                .font(.headline)
                .accessibilityAddTraits(.isHeader)
            Text("Which foods should we avoid?")
                .font(.subheadline)
                .foregroundColor(.secondary)

            VStack(spacing: 8) {
                ForEach(allergenOptions.indices, id: \.self) { index in
                    let option = allergenOptions[index]
                    Button {
                        if answers.allergies.contains(option.value) {
                            answers.allergies.removeAll { $0 == option.value }
                        } else {
                            answers.allergies.append(option.value)
                        }
                        update(answers)
                    } label: {
                        Text(option.label)
                            .font(.subheadline)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(
                                answers.allergies.contains(option.value) ? Color.red.opacity(0.2) : Color.secondary.opacity(0.15)
                            )
                    }
                }
            }
        }
    }

    private func targetsStep(state: OnboardingUiState) -> some View {
        var answers = state.answers
        let calories = state.answers.dailyCalorieTarget ?? 2000
        return VStack(alignment: .leading, spacing: 8) {
            Text("Daily calorie target")
                .font(.headline)
                .accessibilityAddTraits(.isHeader)

            Slider(
                value: Binding(
                    get: { Double(answers.dailyCalorieTarget ?? 2000) },
                    set: { newValue in
                        answers.dailyCalorieTarget = Int(newValue.rounded())
                        update(answers)
                    }
                ),
                in: 0...5000,
            )

            Text("\(calories) kcal")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
    }

    private func errorText(_ error: OnboardingError) -> String {
        switch error {
        case .SAVE_FAILED: return "We could not save your preferences. Try again."
        }
    }
}

/// One selectable onboarding option with a display label (mirrors the shared `OnboardingContent`).
private struct OnboardingOptionItem {
    let value: String
    let label: String
}

private let dietOptions: [OnboardingOptionItem] = [
    OnboardingOptionItem(value: "omnivore", label: "Omnivore"),
    OnboardingOptionItem(value: "vegetarian", label: "Vegetarian"),
    OnboardingOptionItem(value: "vegan", label: "Vegan"),
    OnboardingOptionItem(value: "keto", label: "Keto"),
    OnboardingOptionItem(value: "paleo", label: "Paleo"),
    OnboardingOptionItem(value: "mediterranean", label: "Mediterranean"),
]

private let cuisineOptions: [OnboardingOptionItem] = [
    OnboardingOptionItem(value: "mexican", label: "Mexican"),
    OnboardingOptionItem(value: "italian", label: "Italian"),
    OnboardingOptionItem(value: "asian", label: "Asian"),
    OnboardingOptionItem(value: "mediterranean", label: "Mediterranean"),
    OnboardingOptionItem(value: "american", label: "American"),
    OnboardingOptionItem(value: "indian", label: "Indian"),
]

private let allergenOptions: [OnboardingOptionItem] = [
    OnboardingOptionItem(value: "peanut", label: "Peanut"),
    OnboardingOptionItem(value: "tree nuts", label: "Tree nuts"),
    OnboardingOptionItem(value: "dairy", label: "Dairy"),
    OnboardingOptionItem(value: "egg", label: "Egg"),
    OnboardingOptionItem(value: "gluten", label: "Gluten"),
    OnboardingOptionItem(value: "soy", label: "Soy"),
    OnboardingOptionItem(value: "shellfish", label: "Shellfish"),
    OnboardingOptionItem(value: "fish", label: "Fish"),
    OnboardingOptionItem(value: "sesame", label: "Sesame"),
]

private let excludedOptions: [OnboardingOptionItem] = [
    OnboardingOptionItem(value: "pork", label: "Pork"),
    OnboardingOptionItem(value: "beef", label: "Beef"),
    OnboardingOptionItem(value: "alcohol", label: "Alcohol"),
    OnboardingOptionItem(value: "caffeine", label: "Caffeine"),
    OnboardingOptionItem(value: "added sugar", label: "Added sugar"),
]