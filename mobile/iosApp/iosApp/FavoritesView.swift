import SwiftUI
import Shared
import Foundation

/// The user's favorite recipes (DPL-607): the saved recipes with the heart toggle per row, plus the
/// empty / loading / error states. Backed by the shared `FavoriteRecipesViewModel` -- the same one
/// the Compose screen (DPL-607) uses -- so both platforms render one behaviour.
///
/// The screen reads the view model's current state through `currentState()` after each mutation and
/// keeps it in `@State`, which is what makes SwiftUI re-render on load / toggle / retry.
struct FavoritesView: View {
    @StateObject private var viewModel: FavoriteRecipesViewModel = createFavoriteRecipesViewModel()
    @State private var state: FavoriteRecipesUiState?

    var body: some View {
        Group {
            if let state = state {
                if state.isLoading {
                    loadingView
                } else if let loadError = state.loadError {
                    errorView(loadError: loadError) { Task { await load() } }
                } else if state.recipes.isEmpty {
                    emptyView
                } else {
                    favoritesList(state.recipes, isFavorite: { state.isFavorite($0) })
                }
            }
        }
        .task { await load() }
    }

    // MARK: - state

    func load() async {
        await viewModel.load()
        state = viewModel.currentState()
    }

    func toggle(_ recipe: Recipe) async {
        await viewModel.toggle(recipe)
        state = viewModel.currentState()
    }

    // MARK: - views

    private var loadingView: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading your favorites…")
                .accessibilityLiveRegion(.polite)
        }
    }

    private func errorView(loadError: FavoriteError, retry: @escaping () -> Void) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
            Text("Couldn't load your favorites.")
                .accessibilityLiveRegion(.polite)
            Button("Retry") { retry() }
        }
    }

    private var emptyView: some View {
        VStack(spacing: 12) {
            Image(systemName: "heart")
            Text("No favorite recipes yet.")
            Text("Tap the heart on a recipe to save it here.")
        }
    }

    private func favoritesList(_ recipes: [Recipe], isFavorite: (String) -> Bool) -> some View {
        VStack(spacing: 12) {
            ForEach(recipes.indices, id: \.self) { index in
                if let recipe = recipes[index] {
                    favoriteRow(recipe, isFavorite: isFavorite) {
                        Task { await toggle(recipe) }
                    }
                }
            }
            if state?.isOffline == true {
                Text("Showing your saved favorites. They may be out of date.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
    }

    private func favoriteRow(_ recipe: Recipe, isFavorite: (String) -> Bool, onToggle: @escaping () -> Void) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(recipe.name).font(.subheadline).fontWeight(.semibold)
                if let calories = recipe.nutritionalInfo?.calories {
                    Text("\(calories) kcal")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            Spacer()
            Button {
                onToggle()
            } label: {
                Image(systemName: isFavorite(recipe.id) ? "heart.fill" : "heart")
                    .font(.title2)
            }
            .accessibilityLabel(isFavorite(recipe.id) ? "Remove from favorites" : "Save to favorites")
        }
    }
}

#Preview {
    FavoritesView()
}