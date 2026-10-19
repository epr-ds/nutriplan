package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.NutritionalSummary
import com.nutriplan.shared.data.model.NutrientProgress
import com.nutriplan.shared.data.model.NutritionalTargets

/** The nutrients a plan's summary reports, in display order. */
enum class Nutrient {
    CALORIES,
    PROTEIN,
    CARBS,
    FAT,
    SUGAR,
}

/** How a nutrient's daily average compares with its target. Locale-neutral. */
enum class ProgressStatus {
    /** Below the target (under 100%). */
    UNDER,

    /** Exactly at the target (100%): the server uses an exact match, not a tolerance band. */
    ON_TARGET,

    /** Above the target (over 100%). */
    OVER,

    /** It cannot be judged: there is no target, or not enough data. */
    UNKNOWN,
}

/**
 * One nutrient of a plan's summary, ready to draw as a ring or a bar (DPL-605, DPL-606).
 *
 * [average] is the daily average, [target] the daily goal and [total] the sum over the whole plan;
 * any of them is null when unknown (which is not the same as zero).
 */
data class NutrientRow(
    val nutrient: Nutrient,
    val average: Double?,
    val target: Double?,
    val percentOfTarget: Double?,
    val status: ProgressStatus,
    val total: Double?,
) {
    /** How full the bar is, from 0 to 1 (an overshoot fills it completely), or null when unknown. */
    val barFraction: Float?
        get() = percentOfTarget?.let { (it / PERCENT).coerceIn(0.0, 1.0).toFloat() }

    /** How far the average is above the target; only when [status] is [ProgressStatus.OVER]. */
    val overBy: Double?
        get() = if (status == ProgressStatus.OVER && average != null && target != null) average - target else null

    /** How far the average is below the target; only when [status] is [ProgressStatus.UNDER]. */
    val underBy: Double?
        get() = if (status == ProgressStatus.UNDER && average != null && target != null) target - average else null

    private companion object {
        const val PERCENT = 100.0
    }
}

/** The rows of a plan's nutrition summary; empty when the plan has none. */
data class NutritionSummaryUi(val rows: List<NutrientRow> = emptyList()) {
    /** At least one nutrient has an average to show (a plan without meals has none). */
    val hasData: Boolean get() = rows.any { it.average != null }

    /** The row of [nutrient], if the summary reports it. */
    fun row(nutrient: Nutrient): NutrientRow? = rows.firstOrNull { it.nutrient == nutrient }
}

/**
 * Turns a plan's `nutritionalSummary` into rows for the progress UI, shared by the Compose and
 * SwiftUI screens.
 *
 * The server's per-nutrient progress is used as sent. Where a value is missing the row falls back to
 * what the summary does say (the plan's target and daily average) and derives the percentage and the
 * status the way the server does (under 100% is under, exactly 100% on target, above is over), so a
 * partial payload still draws. A nutrient with neither an average nor a target gets no row; one with
 * a value but no target is shown as [ProgressStatus.UNKNOWN] ("no target set"), never as 0%.
 */
fun NutritionalSummary?.toNutritionSummaryUi(): NutritionSummaryUi {
    val summary = this ?: return NutritionSummaryUi()
    val rows = Nutrient.entries.mapNotNull { nutrient ->
        val progress = summary.progress.of(nutrient)
        val average = progress.actual ?: summary.dailyAverage.of(nutrient)
        val target = progress.target ?: summary.targets.of(nutrient)
        if (average == null && target == null) return@mapNotNull null

        val percent = progress.percentOfTarget
            ?: if (average != null && target != null && target > 0.0) average / target * PERCENT else null
        NutrientRow(
            nutrient = nutrient,
            average = average,
            target = target,
            percentOfTarget = percent,
            status = progress.status.toProgressStatus() ?: percent.toProgressStatus(),
            total = summary.total.of(nutrient),
        )
    }
    return NutritionSummaryUi(rows)
}

private const val PERCENT = 100.0

private fun String?.toProgressStatus(): ProgressStatus? = when (this) {
    "under" -> ProgressStatus.UNDER
    "on_target" -> ProgressStatus.ON_TARGET
    "over" -> ProgressStatus.OVER
    else -> null
}

private fun Double?.toProgressStatus(): ProgressStatus = when {
    this == null -> ProgressStatus.UNKNOWN
    this < PERCENT -> ProgressStatus.UNDER
    this > PERCENT -> ProgressStatus.OVER
    else -> ProgressStatus.ON_TARGET
}

private fun com.nutriplan.shared.data.model.NutritionalProgress.of(nutrient: Nutrient): NutrientProgress =
    when (nutrient) {
        Nutrient.CALORIES -> calories
        Nutrient.PROTEIN -> protein
        Nutrient.CARBS -> carbs
        Nutrient.FAT -> fat
        Nutrient.SUGAR -> sugar
    }

private fun NutritionalInfo?.of(nutrient: Nutrient): Double? = when (nutrient) {
    Nutrient.CALORIES -> this?.calories?.toDouble()
    Nutrient.PROTEIN -> this?.protein
    Nutrient.CARBS -> this?.carbs
    Nutrient.FAT -> this?.fat
    Nutrient.SUGAR -> this?.sugar
}

private fun NutritionalTargets.of(nutrient: Nutrient): Double? = when (nutrient) {
    Nutrient.CALORIES -> calories?.toDouble()
    Nutrient.PROTEIN -> protein?.toDouble()
    Nutrient.CARBS -> carbs?.toDouble()
    Nutrient.FAT -> fat?.toDouble()
    Nutrient.SUGAR -> sugar?.toDouble()
}
