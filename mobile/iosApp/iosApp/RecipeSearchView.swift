import SwiftUI
import Shared
import Foundation

/// The recipe search / browse screen (DPL-602): ingredients, diet type, max calories and min
/// protein filters, the result list with key macros, and the empty / loading / error states.
/// Backed by the shared `RecipeSearchViewModel` -- the same one the Compose screen (DPL-601) uses -
/// so both platforms render one behaviour.
///
/// The screen reads the view model's current state through `currentState()` after each mutation and
/// keeps it in `@State`, which is what makes SwiftUI re-render on input / submit / load more / retry.
struct RecipeSearchView: View {

    @StateObject private var viewModel: RecipeSearchViewModel = createRecipeSearchViewModel()
    @State private var state: RecipeSearchUiState?

    let onRecipeClick: (String) -> Void

    init(onRecipeClick: @escaping (String) -> Void = { _ in }) {
        self.onRecipeClick = onRecipeClick
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                filters
                if let state = state {
                    if state.isLoading && state.recipes.isEmpty {
                        loadingView
                    } else if let error = state.error {
                        errorView(error: error) { Task { await search() } }
                    } else if state.isEmptyResult {
                        emptyView
                    } else if !state.recipes.isEmpty {
                        recipeList(state.recipes)
                        if state.hasMore {
                            Button("Load more") { Task { await loadMore() } }
                                .disabled(state.isLoadingMore)
                        }
                    }
                }
            }
            .padding()
        }
        .task { await search() }
    }

    // MARK: - state

    func search() async {
        await viewModel.search()
        state = viewModel.currentState()
    }

    func loadMore() async {
        await viewModel.loadMore()
        state = viewModel.currentState()
    }

    // MARK: - filters

    private var filters: some View {
        VStack(spacing: 8) {
            TextField("Ingredients", text: Binding(
                get: { state?.ingredients ?? "" },
                set: { viewModel.onIngredientsChange($0); state = viewModel.currentState() }
            ))
            .textInputAutocapitalization(.sentences)
            .autocorrectionDisabled(true)

            Menu {
                Button("Any") { viewModel.onDietTypeChange(nil); state = viewModel.currentState() }
                ForEach(RecipeSearchViewModel.DIET_TYPES, id: \.self) { dietType in
                    Button(dietType) { viewModel.onDietTypeChange(dietType); state = viewModel.currentState() }
                }
            } label: {
                HStack {
                    Text(state?.dietType ?? "Any")
                    Spacer()
                    Image(systemName: "chevron.up.chevron.down")
                }
            }
            .menuStyle(.borderlessButton)

            HStack(spacing: 8) {
                TextField("Max calories", text: Binding(
                    get: { state?.maxCalories ?? "" },
                    set: { viewModel.onMaxCaloriesChange($0); state = viewModel.currentState() }
                ))
                TextField("Min protein", text: Binding(
                    get: { state?.minProtein ?? "" },
                    set: { viewModel.onMinProteinChange($0); state = viewModel.currentState() }
                ))
            }
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled(true)

            Button("Search") { Task { await search() } }
                .disabled(state?.isLoading ?? false)
        }
    }

    // MARK: - views

    private var loadingView: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Searching recipes…")
                .accessibilityLiveRegion(.polite)
        }
    }

    private func errorView(error: RecipeListError, retry: @escaping () -> Void) -> some View {
        HStack {
            Text(errorText(error))
                .font(.subheadline)
                .foregroundColor(.error)
            Button("Retry") { retry() }
        }
    }

    private var emptyView: some View {
        VStack(spacing: 12) {
            Image(systemName: "fork.knife")
            Text("No recipes found.")
            Text("Try different ingredients or fewer filters.")
        }
    }

    private func recipeList(_ recipes: [Recipe]) -> some View {
        VStack(spacing: 12) {
            ForEach(recipes) { recipe in
                recipeRow(recipe) { onRecipeClick(recipe.id) }
            }
        }
    }

    private func recipeRow(_ recipe: Recipe, onClick: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(recipe.name).font(.subheadline).fontWeight(.semibold)
            if let calories = recipe.nutritionalInfo?.calories {
                Text("\(calories) kcal · \(recipe.nutritionalInfo?.protein ?? 0) g protein")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .onTapGesture { onClick() }
    }

    private func errorText(_ error: RecipeListError) -> String {
        switch error {
        case .NETWORK: return "Could not reach the service. Check your connection and try again."
        case .SERVER_PROBLEM: return "The service could not search recipes. Try again."
        case .SESSION_EXPIRED: return "Sign in again to search recipes."
        case .UNKNOWN: return "Something went wrong. Try again."
        }
    }
}

#Preview {
    RecipeSearchView()
}