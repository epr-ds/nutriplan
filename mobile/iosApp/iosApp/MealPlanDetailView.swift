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

            nutritionSection(summary: state?.nutritionalSummaryUi ?? NutritionSummaryUi())

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

    // MARK: - nutrition

    private func nutritionSection(summary: NutritionSummaryUi) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Nutrition")
                .font(.titleMedium)
                .accessibilityAddTraits(.isHeader)

            if summary.hasData {
                ForEach(summary.rows.indices, id: \.self) { index in
                    nutritionRow(summary.rows[index])
                }
            }
        }
    }

    @ViewBuilder
    private func nutritionRow(_ row: NutrientRow) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(nutritionName(row.nutrient))
                .font(.subheadline)
                .fontWeight(.semibold)

            if row.nutrient == Nutrient.CALORIES {
                calorieRing(row: row)
            } else {
                nutrientBar(row: row)
            }
        }
    }

    private func calorieRing(row: NutrientRow) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 12) {
                CircularProgressIndicator(progress: row.barFraction ?? 0)
                    .frame(width: 56, height: 56)
                VStack(alignment: .leading, spacing: 2) {
                    Text(progressText(row))
                    Text(statusText(row.status))
                        .foregroundColor(statusColor(row.status))
                }
            }
            Text(amountText(row))
        }
    }

    private func nutrientBar(row: NutrientRow) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ProgressView(value: row.barFraction ?? 0, total: 1) { Text("") }
            HStack {
                Text(statusText(row.status))
                    .font(.caption)
                    .foregroundColor(statusColor(row.status))
                Spacer()
                Text(amountText(row))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
    }

    private func nutritionName(_ nutrient: Nutrient) -> String {
        switch nutrient {
        case .CALORIES: return "Calories"
        case .PROTEIN: return "Protein"
        case .CARBS: return "Carbs"
        case .FAT: return "Fat"
        case .SUGAR: return "Sugar"
        }
    }

    private func progressText(_ row: NutrientRow) -> String {
        guard let average = row.average, let target = row.target, target > 0 else { return "" }
        return "\(Int(average)) of \(Int(target)) \(row.nutrient == Nutrient.CALORIES ? "kcal" : "g")"
    }

    private func amountText(_ row: NutrientRow) -> String {
        guard let average = row.average else { return "" }
        if let target = row.target { return "\(Int(average)) of \(Int(target)) \(row.nutrient == Nutrient.CALORIES ? "kcal" : "g")" }
        return "\(Int(average)) \(row.nutrient == Nutrient.CALORIES ? "kcal" : "g")"
    }

    private func statusText(_ status: ProgressStatus) -> String {
        switch status {
        case .UNDER: return "Under target"
        case .ON_TARGET: return "On target"
        case .OVER: return "Over target"
        case .UNKNOWN: return "No target set"
        }
    }

    private func statusColor(_ status: ProgressStatus) -> Color {
        switch status {
        case .OVER: return .error
        case .ON_TARGET: return .green
        case .UNDER: return .primary
        case .UNKNOWN: return .secondary
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