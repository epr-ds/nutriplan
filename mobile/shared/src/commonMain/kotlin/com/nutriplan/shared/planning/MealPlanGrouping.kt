package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.PlanMeal

/** One day of a plan: its meals grouped by meal type, in the order people eat them. */
data class MealPlanDay(
    /** ISO date (`yyyy-MM-dd`) as sent by the server; the platform formats it for display. */
    val date: String,
    val sections: List<MealSection>,
) {
    /** Sum of the known per-meal calories, or null when no meal of the day has calories. */
    val totalCalories: Int?
        get() = sections.flatMap { it.meals }.mapNotNull { it.calories }.takeIf { it.isNotEmpty() }?.sum()
}

/** The meals of one meal type on one day. [mealType] is the server value, e.g. `BREAKFAST`. */
data class MealSection(
    val mealType: String,
    val meals: List<PlanMeal>,
)

private val MEAL_TYPE_ORDER = listOf("BREAKFAST", "LUNCH", "DINNER", "SNACK")

/**
 * Groups [meals] by day and meal type (DPL-505).
 *
 * - Days are sorted by date (ISO dates sort correctly as text).
 * - Within a day the sections follow breakfast, lunch, dinner, snack; unknown meal types come
 *   after those, alphabetically, so a type the app does not know yet is still shown.
 * - Meals of the same section keep the order they arrived in.
 * - Meal types are compared case-insensitively but displayed as sent.
 */
fun groupMealsByDay(meals: List<PlanMeal>): List<MealPlanDay> =
    meals
        .groupBy { it.scheduledDate }
        .entries
        .sortedBy { it.key }
        .map { (date, dayMeals) ->
            val sections = dayMeals
                .groupBy { it.mealType.uppercase() }
                .entries
                .sortedWith(
                    compareBy<Map.Entry<String, List<PlanMeal>>> { entry ->
                        MEAL_TYPE_ORDER.indexOf(entry.key).let { if (it < 0) MEAL_TYPE_ORDER.size else it }
                    }.thenBy { it.key },
                )
                .map { (_, sectionMeals) -> MealSection(mealType = sectionMeals.first().mealType, meals = sectionMeals) }
            MealPlanDay(date = date, sections = sections)
        }
