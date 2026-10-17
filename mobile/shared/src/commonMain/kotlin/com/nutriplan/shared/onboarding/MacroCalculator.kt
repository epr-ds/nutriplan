package com.nutriplan.shared.onboarding

import com.nutriplan.shared.data.model.DietaryMacroTargets

/**
 * Defaults for the calorie/macro step (IDN-604).
 *
 * Values respect the `DietaryPreferencesRequest` bounds (`dailyCalorieTarget` 1200–5000) and split
 * the target 30% protein / 40% carbohydrates / 30% fat — the conventional balanced starting point
 * a user can adjust later in profile settings.
 */
object MacroCalculator {

    const val MIN_CALORIES = 1200
    const val MAX_CALORIES = 5000
    const val DEFAULT_CALORIES = 2000

    private const val KCAL_PER_PROTEIN = 4
    private const val KCAL_PER_CARB = 4
    private const val KCAL_PER_FAT = 9

    private const val PROTEIN_SHARE = 0.30
    private const val CARB_SHARE = 0.40
    private const val FAT_SHARE = 0.30

    /** Clamp a calorie target into the contract's allowed range. */
    fun clampCalories(calories: Int): Int = calories.coerceIn(MIN_CALORIES, MAX_CALORIES)

    /** A balanced macro split (grams) for [calories], clamped to the allowed range. */
    fun defaultMacroTargets(calories: Int): DietaryMacroTargets {
        val safe = clampCalories(calories)
        return DietaryMacroTargets(
            proteinGrams = grams(safe, PROTEIN_SHARE, KCAL_PER_PROTEIN),
            carbsGrams = grams(safe, CARB_SHARE, KCAL_PER_CARB),
            fatGrams = grams(safe, FAT_SHARE, KCAL_PER_FAT),
        )
    }

    private fun grams(calories: Int, share: Double, kcalPerGram: Int): Int =
        ((calories * share) / kcalPerGram).toInt()
}
