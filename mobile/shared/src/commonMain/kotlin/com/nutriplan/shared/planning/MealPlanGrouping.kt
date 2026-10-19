package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.PlanMeal

/**
 * One day of a plan: its meals grouped by meal type, in the order people eat them.
 *
 * The API places a meal on a day by its 0-based [dayIndex] within the plan's inclusive date range;
 * [date] is that day's calendar date (ISO `yyyy-MM-dd`), or null when it cannot be worked out. A day
 * with a null [dayIndex] collects the meals that are not assigned to a day yet.
 */
data class MealPlanDay(
    val dayIndex: Int?,
    val date: String?,
    val sections: List<MealSection>,
) {
    /** Sum of the known per-meal calories, or null when no meal of the day has calories. */
    val totalCalories: Int?
        get() = sections
            .flatMap { it.meals }
            .mapNotNull { it.nutritionalInfo?.calories }
            .takeIf { it.isNotEmpty() }
            ?.sum()
}

/** The meals of one meal type on one day. [mealType] is the server value, e.g. `breakfast`. */
data class MealSection(
    val mealType: String,
    val meals: List<PlanMeal>,
)

private val MEAL_TYPE_ORDER = listOf("BREAKFAST", "LUNCH", "DINNER", "SNACK")

/**
 * Groups [meals] by day and meal type (DPL-505).
 *
 * - Days are sorted by day index; meals without a day come last as one unassigned day.
 * - Within a day the sections follow breakfast, lunch, dinner, snack; unknown meal types come
 *   after those, alphabetically, so a type the app does not know yet is still shown.
 * - Meals of the same section keep the order they arrived in.
 * - Meal types are compared case-insensitively but displayed as sent.
 *
 * @param startDate the plan's start date (ISO), the date of day index 0.
 */
fun groupMealsByDay(startDate: String, meals: List<PlanMeal>): List<MealPlanDay> =
    meals
        .groupBy { it.dayIndex }
        .entries
        .sortedWith(compareBy<Map.Entry<Int?, List<PlanMeal>>> { it.key == null }.thenBy { it.key ?: 0 })
        .map { (dayIndex, dayMeals) ->
            MealPlanDay(
                dayIndex = dayIndex,
                date = dayIndex?.let { IsoDate.addDays(startDate, it) },
                sections = sectionsOf(dayMeals),
            )
        }

private fun sectionsOf(dayMeals: List<PlanMeal>): List<MealSection> =
    dayMeals
        .groupBy { it.mealType.uppercase() }
        .entries
        .sortedWith(
            compareBy<Map.Entry<String, List<PlanMeal>>> { entry ->
                MEAL_TYPE_ORDER.indexOf(entry.key).let { if (it < 0) MEAL_TYPE_ORDER.size else it }
            }.thenBy { it.key },
        )
        .map { (_, sectionMeals) -> MealSection(mealType = sectionMeals.first().mealType, meals = sectionMeals) }
