import SwiftUI
import Shared
import Foundation

/// The user's meal plans, newest first, with the empty / loading / error states and pull-to-refresh,
/// plus a tap through to the plan detail. Backed by the shared `MealPlanListViewModel` -- the same
/// one the Compose screen (DPL-501) uses -- so both platforms render one behaviour.
///
/// The screen reads the view model's current state through `currentState()` after each mutation and
/// keeps it in `@State`, which is what makes SwiftUI re-render on load / refresh / retry.
struct MealPlanListView: View {
    @StateObject private var viewModel: MealPlanListViewModel = createMealPlanListViewModel()
    @State private var state: MealPlanListUiState?

    let onPlanClick: (String) -> Void

    init(onPlanClick: @escaping (String) -> Void = { _ in }) {
        self.onPlanClick = onPlanClick
    }

    var body: some View {
        Group {
            if let state = state {
                if state.isLoading {
                    loadingView
                } else if let error = state.error {
                    errorView(error: error) { Task { await load() } }
                } else if state.plans.isEmpty {
                    emptyView
                } else {
                    planList(state.plans)
                }
            }
        }
        .refreshable { await refresh() }
        .task { await load() }
    }

    // MARK: - state

    func load() async {
        await viewModel.load()
        state = viewModel.currentState()
    }

    func refresh() async {
        await viewModel.refresh()
        state = viewModel.currentState()
    }

    // MARK: - views

    private var loadingView: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading your meal plans…")
                .accessibilityLiveRegion(.polite)
        }
    }

    private func errorView(error: MealPlanListError, retry: @escaping () -> Void) -> some View {
        HStack {
            Text(errorText(error))
                .font(.subheadline)
                .foregroundColor(.error)
            Button("Retry") { retry() }
        }
    }

    private var emptyView: some View {
        VStack(spacing: 12) {
            Image(systemName: "calendar")
            Text("No meal plans yet.")
            Text("Create a meal plan to start planning your meals.")
        }
    }

    private func planList(_ plans: [MealPlanSummary]) -> some View {
        VStack(spacing: 12) {
            ForEach(plans.indices, id: \.self) { index in
                planRow(plan: plans[index]) { onPlanClick(plans[index].id) }
            }
        }
    }

    private func planRow(_ plan: MealPlanSummary, onClick: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(plan.name).font(.subheadline).fontWeight(.semibold)
            Text("\(plan.startDate) → \(plan.endDate)")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .onTapGesture { onClick() }
    }

    private func errorText(_ error: MealPlanListError) -> String {
        switch error {
        case .NETWORK: return "Could not reach the service. Check your connection and try again."
        case .SERVER_PROBLEM: return "The service could not load your meal plans. Try again."
        case .SESSION_EXPIRED: return "Sign in again to see your meal plans."
        case .UNKNOWN: return "Something went wrong. Try again."
        }
    }
}

#Preview {
    MealPlanListView()
}