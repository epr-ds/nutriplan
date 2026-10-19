package com.nutriplan.android.screen.plans

import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.shared.planning.Nutrient
import com.nutriplan.shared.planning.NutrientRow
import com.nutriplan.shared.planning.NutritionSummaryUi
import com.nutriplan.shared.planning.ProgressStatus
import java.text.NumberFormat

/** Test tags for the nutrition summary (used by the Robolectric UI tests). */
object NutritionSummaryTestTags {
    const val CARD = "nutrition_summary_card"
    const val ROW = "nutrition_summary_row"
    const val RING = "nutrition_summary_ring"
    const val BAR = "nutrition_summary_bar"
    const val TOTAL = "nutrition_summary_total"
}

/**
 * DPL-605 / DPL-606: the plan's daily average against its daily targets: a ring for calories, bars
 * for the macros, each with its status in words ("Under target", "On target", "Over target") so
 * over and under never depend on colour alone, and the plan total underneath. Each row reads as one
 * sentence to a screen reader. Shows nothing when [summary] has no data (a plan without meals).
 */
@Composable
fun NutritionSummaryCard(summary: NutritionSummaryUi, modifier: Modifier = Modifier) {
    if (!summary.hasData) return

    Card(
        modifier = modifier
            .fillMaxWidth()
            .testTag(NutritionSummaryTestTags.CARD),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Column {
                Text(
                    text = stringResource(R.string.nutrition_title),
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.semantics { heading() },
                )
                Text(
                    text = stringResource(R.string.nutrition_subtitle),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            summary.rows.forEach { row ->
                if (row.nutrient == Nutrient.CALORIES) CaloriesRing(row) else NutrientBar(row)
            }

            val total = totalText(summary)
            if (total.isNotEmpty()) {
                Text(
                    text = stringResource(R.string.nutrition_total, total),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.testTag(NutritionSummaryTestTags.TOTAL),
                )
            }
        }
    }
}

@Composable
private fun CaloriesRing(row: NutrientRow) {
    val color = row.status.color()
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(NutritionSummaryTestTags.ROW)
            .semantics(mergeDescendants = true) {},
        horizontalArrangement = Arrangement.spacedBy(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(contentAlignment = Alignment.Center) {
            // The text beside the ring says the same in words.
            CircularProgressIndicator(
                progress = { row.barFraction ?: 0f },
                modifier = Modifier
                    .size(72.dp)
                    .testTag(NutritionSummaryTestTags.RING),
                color = color,
                trackColor = MaterialTheme.colorScheme.surfaceVariant,
                strokeWidth = 8.dp,
            )
            row.percentOfTarget?.let {
                Text(
                    text = stringResource(R.string.nutrition_percent, it.toInt()),
                    style = MaterialTheme.typography.labelLarge,
                )
            }
        }
        Column {
            Text(text = stringResource(row.nutrient.labelRes()), style = MaterialTheme.typography.titleSmall)
            Text(text = amountText(row), style = MaterialTheme.typography.bodyLarge)
            Text(text = statusText(row), style = MaterialTheme.typography.bodyMedium, color = color)
        }
    }
}

@Composable
private fun NutrientBar(row: NutrientRow) {
    val color = row.status.color()
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(NutritionSummaryTestTags.ROW)
            .semantics(mergeDescendants = true) {},
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(text = stringResource(row.nutrient.labelRes()), style = MaterialTheme.typography.titleSmall)
            Text(text = amountText(row), style = MaterialTheme.typography.bodyMedium)
        }
        LinearProgressIndicator(
            progress = { row.barFraction ?: 0f },
            modifier = Modifier
                .fillMaxWidth()
                .testTag(NutritionSummaryTestTags.BAR),
            color = color,
            trackColor = MaterialTheme.colorScheme.surfaceVariant,
        )
        Text(text = statusText(row), style = MaterialTheme.typography.bodySmall, color = color)
    }
}

/** Over is an error colour, on target a positive one, under the neutral accent; unknown is muted. */
@Composable
private fun ProgressStatus.color(): Color = when (this) {
    ProgressStatus.OVER -> MaterialTheme.colorScheme.error
    ProgressStatus.ON_TARGET -> MaterialTheme.colorScheme.tertiary
    ProgressStatus.UNDER -> MaterialTheme.colorScheme.primary
    ProgressStatus.UNKNOWN -> MaterialTheme.colorScheme.onSurfaceVariant
}

@StringRes
private fun Nutrient.labelRes(): Int = when (this) {
    Nutrient.CALORIES -> R.string.nutrient_calories
    Nutrient.PROTEIN -> R.string.nutrient_protein
    Nutrient.CARBS -> R.string.nutrient_carbs
    Nutrient.FAT -> R.string.nutrient_fat
    Nutrient.SUGAR -> R.string.nutrient_sugar
}

/** "1,800 of 2,000 kcal", "85 g" when there is no target, or "Not enough data" when there is no average. */
@Composable
private fun amountText(row: NutrientRow): String {
    val average = row.average ?: return stringResource(R.string.nutrition_no_data)
    val isCalories = row.nutrient == Nutrient.CALORIES
    val target = row.target
    return when {
        target != null -> stringResource(
            if (isCalories) R.string.nutrition_kcal_of_target else R.string.nutrition_g_of_target,
            formatAmount(average),
            formatAmount(target),
        )
        else -> stringResource(
            if (isCalories) R.string.nutrition_kcal else R.string.nutrition_g,
            formatAmount(average),
        )
    }
}

/** The status in words ("Under target", "On target", "Over target"): it never relies on colour alone. */
@Composable
private fun statusText(row: NutrientRow): String = when (row.status) {
    ProgressStatus.UNDER -> stringResource(R.string.nutrition_status_under)
    ProgressStatus.ON_TARGET -> stringResource(R.string.nutrition_status_on_target)
    ProgressStatus.OVER -> stringResource(R.string.nutrition_status_over)
    ProgressStatus.UNKNOWN ->
        stringResource(if (row.target == null) R.string.nutrition_status_no_target else R.string.nutrition_no_data)
}

/** "5,200 kcal · Protein 310 g · Carbs 400 g", only the nutrients the plan has totals for. */
@Composable
private fun totalText(summary: NutritionSummaryUi): String {
    val parts = summary.rows.mapNotNull { row ->
        val total = row.total ?: return@mapNotNull null
        when (row.nutrient) {
            Nutrient.CALORIES -> stringResource(R.string.nutrition_kcal, formatAmount(total))
            Nutrient.PROTEIN -> stringResource(R.string.recipe_nutrition_protein, formatAmount(total))
            Nutrient.CARBS -> stringResource(R.string.recipe_nutrition_carbs, formatAmount(total))
            Nutrient.FAT -> stringResource(R.string.recipe_nutrition_fat, formatAmount(total))
            Nutrient.SUGAR -> stringResource(R.string.recipe_nutrition_sugar, formatAmount(total))
        }
    }
    return parts.joinToString(" · ")
}

/** A number in the user's locale with at most one decimal ("1,800", "32.5"). */
private fun formatAmount(value: Double): String =
    NumberFormat.getInstance().apply { maximumFractionDigits = 1 }.format(value)
