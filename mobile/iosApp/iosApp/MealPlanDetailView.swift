import SwiftUI
import Shared
import Foundation

/// The detail of one meal plan: its days, each with the meals grouped by meal type (DPL-506).
/// Backed by the shared `MealPlanDetailViewModel` -- the same one the Compose screen (DPL-505) uses
/// -- so both platforms render one behaviour.
///
/// The screen reads the view model's current state through `currentState()` after each mutation and
/// keeps it in `@State`, which is what makes SwiftUI re-render on load / refresh / retry.
struct MealPlanDetailView: View {
    @StateObject private var viewModel: MealPlanDetailViewModel = createMealPlanDetailViewModel()
    @State private var state: MealPlanDetailUiState?

    let planId: String
    let onBack: () -> Void

    init(planId: String, onBack: @escaping () -> Void = {}) {
        self.planId = planId
        self.onBack = onBack
    }

    var body: some View {
        Group {
            if let state = state {
                if state.isLoading {
                    loadingView
                } else if let error = state.error {
                    errorView(error: error) { Task { await load() } }
                } else if let plan = state.plan {
                    planDetail(plan: plan, days: state.days)
                }
            }
        }
        .task { await load() }
    }

    // MARK: - state

    func load() async {
        await viewModel.load(planId)
        state = viewModel.currentState()
    }

    // MARK: - views

    private var loadingView: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading your meal plan…")
                .accessibilityLiveRegion(.polite)
        }
    }

    private func errorView(error: MealPlanDetailError, retry: @escaping () -> Void) -> some View {
        HStack {
            Text(errorText(error))
                .font(.subheadline)
                .foregroundColor(.error)
            Button("Retry") { retry() }
        }
    }

    private func planDetail(plan: MealPlan, days: [MealPlanDay]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(plan.name).font(.title).accessibilityAddTraits(.isHeader)
            Text("\(plan.startDate) → \(plan.endDate)")
                .font(.caption)
                .foregroundColor(.secondary)

            if days.isEmpty {
                Text("This meal plan has no meals yet.")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }

            ForEach(days.indices, id: \.self) { index in
                daySection(day: days[index])
            }
        }
    }

    private func daySection(day: MealPlanDay) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Day \(day.dayIndex ?? 0): \(day.date ?? "")")
                .font(.subheadline)
                .fontWeight(.semibold)

            ForEach(day.sections.indices, id: \.self) { sectionIndex in
                let section = day.sections[sectionIndex]
                VStack(alignment: .leading, spacing: 4) {
                    Text(section.mealType)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    ForEach(section.meals.indices, id: \.self) { mealIndex in
                        mealRow(section.meals[mealIndex])
                    }
                }
            }
        }
    }

    private func mealRow(_ meal: PlanMeal) -> some View {
        HStack {
            Text("\(meal.mealType) · \(meal.servings ?? 0) servings")
                .font(.subheadline)
            Spacer()
            if let calories = meal.nutritionalInfo?.calories {
                Text("\(calories) kcal")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
        }
    }

    private func errorText(_ error: MealPlanDetailError) -> String {
        switch error {
        case .NETWORK: return "Could not reach the service. Check your connection and try again."
        case .SERVER_PROBLEM: return "The service could not load your meal plan. Try again."
        case .NOT_FOUND: return "This meal plan is no longer available."
        case .SESSION_EXPIRED: return "Sign in again to see your meal plan."
        case .UNKNOWN: return "Something went wrong. Try again."
        }
    }
}

#Preview {
    MealPlanDetailView(planId: "p1")
}