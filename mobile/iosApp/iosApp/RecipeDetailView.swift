import SwiftUI
import Shared
import Foundation

/// The detail of one recipe: its description, ingredients, instructions, nutrition and the
/// server's nutrition disclaimer. Backed by the shared `RecipeDetailViewModel` -- the same one the
/// Compose screen (DPL-603) uses -- so both platforms render one behaviour.
///
/// The screen reads the view model's current state through `currentState()` after each mutation and
/// keeps it in `@State`, which is what makes SwiftUI re-render on load / refresh / retry.
struct RecipeDetailView: View {
    @StateObject private var viewModel: RecipeDetailViewModel = createRecipeDetailViewModel()
    @State private var state: RecipeDetailUiState?

    let recipeId: String
    let onBack: () -> Void

    init(recipeId: String, onBack: @escaping () -> Void = {}) {
        self.recipeId = recipeId
        self.onBack = onBack
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            ScrollView {
                VStack(spacing: 0) {
                    if let state = state {
                        if state.isLoading {
                            loadingView
                        } else if let error = state.error {
                            errorView { Task { await load() } }
                        } else if let recipe = state.recipe {
                            detail(recipe: recipe, disclaimer: state.disclaimer)
                        }
                    }
                }
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    // MARK: - views

    private var header: some View {
        HStack {
            Button(action: onBack) {
                Image(systemName: "chevron.left")
                    .font(.subheadline)
                    .foregroundColor(.primary)
            }
            .accessibilityLabel("Back")

            Text("Recipe")
                .font(.headline)
                .accessibilityAddTraits(.isHeader)

            Spacer()
        }
        .padding()
    }

    private var loadingView: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading the recipe")
                .accessibilityLiveRegion(.polite)
        }
    }

    private func errorView(retry: @escaping () -> Void) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
            Text("Couldn't load this recipe.")
                .accessibilityLiveRegion(.polite)
            Button("Retry") { retry() }
        }
    }

    // MARK: - content

    private func detail(recipe: Recipe, disclaimer: NutritionDisclaimer?) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(recipe.name)
                .font(.title)
                .accessibilityAddTraits(.isHeader)

            Text(nutritionText(recipe: recipe))
                .font(.subheadline)
                .foregroundColor(.secondary)

            if let description = recipe.description {
                Text(description)
                    .font(.body)
            }

            metaRows(recipe: recipe)

            sectionHeading("Ingredients")
            ingredientList(recipe: recipe)

            sectionHeading("Instructions")
            instructionList(recipe: recipe)

            sectionHeading("Nutrition")
            nutritionSection(recipe: recipe)

            if let disclaimer = disclaimer {
                Text(disclaimer.disclaimer)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding(16)
    }

    private func metaRows(recipe: Recipe) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            if recipe.servings != nil {
                Text("Servings: \(recipe.servings ?? 0)")
            }
            if recipe.prepTime != nil {
                Text("Prep: \(recipe.prepTime ?? 0) min")
            }
            if recipe.cookTime != nil {
                Text("Cook: \(recipe.cookTime ?? 0) min")
            }
        }
    }

    private func ingredientList(recipe: Recipe) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(recipe.ingredients.indices, id: \.self) { index in
                if let ingredient = recipe.ingredients[index] {
                    Text("\(ingredient.name) — \(ingredient.quantity ?? 0) \(ingredient.unit ?? "")")
                        .font(.subheadline)
                }
            }
        }
    }

    private func instructionList(recipe: Recipe) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(recipe.instructions.indices, id: \.self) { index in
                Text("\(index + 1). \(recipe.instructions[index] ?? "")")
                    .font(.subheadline)
            }
        }
    }

    private func nutritionText(recipe: Recipe) -> String {
        guard let nutrition = recipe.nutritionalInfo else { return "Nutrition: —" }
        var parts: [String] = []
        if let calories = nutrition.calories { parts.append("\(calories) kcal") }
        if let protein = nutrition.protein { parts.append("\(Int(protein.rounded())) g protein") }
        if let carbs = nutrition.carbs { parts.append("\(Int(carbs.rounded())) g carbs") }
        if let fat = nutrition.fat { parts.append("\(Int(fat.rounded())) g fat") }
        if let sugar = nutrition.sugar { parts.append("\(Int(sugar.rounded())) g sugar") }
        return "Nutrition: \(parts.joined(separator: " · "))"
    }

    private func nutritionSection(recipe: Recipe) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(nutritionText(recipe: recipe))
        }
    }

    private func sectionHeading(_ title: String) -> some View {
        Text(title)
            .font(.titleMedium)
            .accessibilityAddTraits(.isHeader)
    }

    // MARK: - actions

    private func load() async {
        await viewModel.load(recipeId)
        state = viewModel.currentState()
    }
}

#Preview {
    RecipeDetailView(recipeId: "r1")
}