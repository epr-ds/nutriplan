import SwiftUI
import Shared
import Foundation

/// The edit-meal form (DPL-508 and meal editing): show the planned meal, choose a satisfaction
/// rating (1 to 5) and save. Backed by the shared `EditMealViewModel` -- the same one the Compose
/// screen (DPL-508) uses -- so both platforms render one behaviour.
///
/// The screen reads the view model's current state through `currentState()` after each mutation and
/// keeps it in `@State`, which is what makes SwiftUI re-render on load / save / retry.
struct EditMealView: View {
    @StateObject private var viewModel: EditMealViewModel = createEditMealViewModel()
    @State private var state: EditMealUiState?

    let planId: String
    let mealId: String
    let onDone: () -> Void

    init(planId: String, mealId: String, onDone: @escaping () -> Void = {}) {
        self.planId = planId
        self.mealId = mealId
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
                    } else if let meal = state.meal {
                        mealSection(meal: meal, state: state)
                    }
                }
            }
            .padding()
        }
    }

    // MARK: - state

    func load() async {
        await viewModel.start(planId: planId, mealId: mealId)
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
            Text("Loading the meal…")
                .accessibilityLiveRegion(.polite)
        }
    }

    private var satisfactionText: String {
        state?.satisfaction.map { String($0) } ?? "Not rated"
    }

    private func errorView(loadError: EditMealError, retry: @escaping () -> Void) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
            Text("Couldn't edit this meal.")
                .accessibilityLiveRegion(.polite)
            Button("Retry") { retry() }
        }
    }

    private func mealSection(meal: PlanMeal, state: EditMealUiState) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(meal.mealType ?? "Meal")
                .font(.title)
                .accessibilityAddTraits(.isHeader)

            Text("Satisfaction: \(satisfactionText)")

            Menu {
                Button("1") { viewModel.onSatisfactionChange(1); state = viewModel.currentState() }
                Button("2") { viewModel.onSatisfactionChange(2); state = viewModel.currentState() }
                Button("3") { viewModel.onSatisfactionChange(3); state = viewModel.currentState() }
                Button("4") { viewModel.onSatisfactionChange(4); state = viewModel.currentState() }
                Button("5") { viewModel.onSatisfactionChange(5); state = viewModel.currentState() }
            } label: {
                HStack {
                    Text(state.satisfaction.map { String($0) } ?? "Not rated")
                    Spacer()
                    Image(systemName: "chevron.up.chevron.down")
                }
            }
            .menuStyle(.borderlessButton)

            Button("Save meal") { Task { await save() } }
                .disabled(state.isSaving)
        }
    }
}

#Preview {
    EditMealView(planId: "p1", mealId: "m1")
}