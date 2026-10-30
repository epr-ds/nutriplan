import SwiftUI
import Shared
import Foundation

/// The add-meal form (DPL-507): pick a recipe, choose the meal type and servings, and (optionally) a
/// day of the plan, then save. Backed by the shared `AddMealViewModel` -- the same one the Compose
/// screen (DPL-507) uses -- so both platforms render one behaviour.
///
/// The screen reads the view model's current state through `currentState()` after each mutation and
/// keeps it in `@State`, which is what makes SwiftUI re-render on load / save / retry.
struct AddMealView: View {
    /// The meal types the add-meal form offers (mirrors [AddMealViewModel.MEAL_TYPES]).
    private static let mealTypes = ["breakfast", "lunch", "dinner", "snack"]

    @StateObject private var viewModel: AddMealViewModel = createAddMealViewModel()
    @State private var state: AddMealUiState?

    let planId: String
    let recipeId: String
    let onDone: () -> Void

    init(planId: String, recipeId: String, onDone: @escaping () -> Void = {}) {
        self.planId = planId
        self.recipeId = recipeId
        self.onDone = onDone
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if let state = state {
                    if state.isLoading {
                        loadingView
                    } else if let loadError = state.loadError {
                        errorView(loadError: loadError) { Task { await load() } }
                    } else if let recipe = state.recipe {
                        recipeSection(recipe: recipe, state: state)
                    }
                }
            }
            .padding()
        }
    }

    // MARK: - state

    func load() async {
        await viewModel.start(planId: planId, recipeId: recipeId)
        state = viewModel.currentState()
    }

    func save() async {
        await viewModel.save()
        state = viewModel.currentState()
        if state?.isDone == true { onDone() }
    }

    // MARK: - views

    private var loadingView: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading the recipe…")
                .accessibilityLiveRegion(.polite)
        }
    }

    private func errorView(loadError: AddMealError, retry: @escaping () -> Void) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
            Text("Couldn't add this meal.")
                .accessibilityLiveRegion(.polite)
            Button("Retry") { retry() }
        }
    }

    private func recipeSection(recipe: Recipe, state: AddMealUiState) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(recipe.name)
                .font(.title)
                .accessibilityAddTraits(.isHeader)

            if let mealTypeError = state.mealTypeError {
                Text(fieldErrorText(mealTypeError))
                    .font(.caption)
                    .foregroundColor(.error)
            }
            if let servingsError = state.servingsError {
                Text(fieldErrorText(servingsError))
                    .font(.caption)
                    .foregroundColor(.error)
            }
            if let error = state.error {
                errorBanner(error: error) { Task { await save() } }
            }

            Menu {
                ForEach(Self.mealTypes.indices, id: \.self) { index in
                    Button("\(Self.mealTypes[index])") { viewModel.onMealTypeChange(Self.mealTypes[index]); state = viewModel.currentState() }
                }
            } label: {
                HStack {
                    Text(state.mealType ?? "Meal type")
                    Spacer()
                    Image(systemName: "chevron.up.chevron.down")
                }
            }
            .menuStyle(.borderlessButton)

            TextField("Servings", text: Binding(
                get: { state.servings },
                set: { viewModel.onServingsChange($0); state = viewModel.currentState() }
            ))
            .keyboardType(.decimalPad)

            Menu {
                Button("No day") { viewModel.onDayChange(nil); state = viewModel.currentState() }
                ForEach(state.days.indices, id: \.self) { index in
                    let day = state.days[index]
                    Button(day.date ?? "Day \(day.dayIndex)") { viewModel.onDayChange(day.dayIndex) }
                }
            } label: {
                HStack {
                    Text(selectedDayText)
                    Spacer()
                    Image(systemName: "chevron.up.chevron.down")
                }
            }
            .menuStyle(.borderlessButton)

            Button("Save meal") { Task { await save() } }
                .disabled(state.isSaving)
        }
    }

    private var selectedDayText: String {
        guard let dayIndex = state?.dayIndex else { return "No day" }
        return state?.days.first { $0.dayIndex == dayIndex }?.date ?? "Day \(dayIndex)"
    }

    private func errorBanner(error: AddMealError, retry: @escaping () -> Void) -> some View {
        HStack {
            Text(errorText(error))
                .font(.subheadline)
                .foregroundColor(.error)
            Button("Retry") { retry() }
        }
    }

    private func fieldErrorText(_ error: AddMealFieldError) -> String {
        switch error {
        case .MEAL_TYPE_REQUIRED: return "Choose the meal type."
        case .SERVINGS_REQUIRED: return "Enter the servings."
        case .SERVINGS_INVALID: return "Enter the servings as a number."
        }
    }

    private func errorText(_ error: AddMealError) -> String {
        switch error {
        case .NETWORK: return "The device could not reach the service. Meals cannot be added offline yet."
        case .SERVER_PROBLEM: return "The service could not add the meal. Try again."
        case .SESSION_EXPIRED: return "Sign in again to add this meal."
        case .NOT_FOUND: return "This recipe is no longer available."
        case .REJECTED: return "The meal could not be added. Try again."
        case .UNKNOWN: return "Something went wrong. Try again."
        }
    }
}

#Preview {
    AddMealView(planId: "p1", recipeId: "r1")
}