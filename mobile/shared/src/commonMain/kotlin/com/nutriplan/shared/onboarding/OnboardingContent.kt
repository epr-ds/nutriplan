package com.nutriplan.shared.onboarding

/** A selectable onboarding option with bilingual (es/en) labels. */
data class OnboardingOption(
    val value: String,
    val labelEn: String,
    val labelEs: String,
)

/**
 * Onboarding catalogs (IDN-902/903).
 *
 * The `value` of every option matches the `DietaryPreferencesRequest` enums in
 * `contracts/identity.openapi.yaml`; only the labels are presentation. Allergens and excluded
 * ingredients are free-form strings in the contract, so those lists are a curated starting point
 * the UI can extend.
 */
object OnboardingContent {

    val dietTypes: List<OnboardingOption> = listOf(
        OnboardingOption("omnivore", "Omnivore", "Omnívoro"),
        OnboardingOption("vegetarian", "Vegetarian", "Vegetariano"),
        OnboardingOption("vegan", "Vegan", "Vegano"),
        OnboardingOption("keto", "Keto", "Cetogénica"),
        OnboardingOption("paleo", "Paleo", "Paleo"),
        OnboardingOption("mediterranean", "Mediterranean", "Mediterránea"),
    )

    val cuisines: List<OnboardingOption> = listOf(
        OnboardingOption("mexican", "Mexican", "Mexicana"),
        OnboardingOption("italian", "Italian", "Italiana"),
        OnboardingOption("asian", "Asian", "Asiática"),
        OnboardingOption("mediterranean", "Mediterranean", "Mediterránea"),
        OnboardingOption("american", "American", "Estadounidense"),
        OnboardingOption("indian", "Indian", "India"),
    )

    val commonAllergens: List<OnboardingOption> = listOf(
        OnboardingOption("peanut", "Peanut", "Cacahuate"),
        OnboardingOption("tree nuts", "Tree nuts", "Frutos secos"),
        OnboardingOption("dairy", "Dairy", "Lácteos"),
        OnboardingOption("egg", "Egg", "Huevo"),
        OnboardingOption("gluten", "Gluten", "Gluten"),
        OnboardingOption("soy", "Soy", "Soya"),
        OnboardingOption("shellfish", "Shellfish", "Mariscos"),
        OnboardingOption("fish", "Fish", "Pescado"),
        OnboardingOption("sesame", "Sesame", "Sésamo"),
    )

    val commonExcludedIngredients: List<OnboardingOption> = listOf(
        OnboardingOption("pork", "Pork", "Cerdo"),
        OnboardingOption("beef", "Beef", "Res"),
        OnboardingOption("alcohol", "Alcohol", "Alcohol"),
        OnboardingOption("caffeine", "Caffeine", "Cafeína"),
        OnboardingOption("added sugar", "Added sugar", "Azúcar añadida"),
    )
}
