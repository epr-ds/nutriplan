package com.nutriplan.shared.planning

/** The most days a plan's day choice lists; a plan is a few days to a few weeks. */
private const val MAX_PLAN_DAYS = 366

/**
 * The days of a plan between [startDate] and [endDate] (inclusive, ISO `yyyy-MM-dd`), each with the
 * 0-based index the API places a meal by. Empty when either date is not a valid date or the range
 * is backwards.
 */
fun planDays(startDate: String, endDate: String): List<PlanDayOption> {
    val count = (IsoDate.daysBetween(startDate, endDate) ?: return emptyList()) + 1
    return (0 until count.coerceAtMost(MAX_PLAN_DAYS)).mapNotNull { index ->
        IsoDate.addDays(startDate, index)?.let { PlanDayOption(index, it) }
    }
}
