package com.nutriplan.android.screen.plans

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.matchParentSize
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import com.nutriplan.android.R
import com.nutriplan.shared.planning.PlanDayOption

/**
 * The day of a plan, chosen from a menu ("Day 3 · Saturday, October 3, 2026"). (A read-only text
 * field swallows taps, so a transparent clickable area sits over it.) [allowNone] adds a "No day
 * yet" entry; leave it off when the meal already has a day, which the API cannot take away.
 */
@Composable
internal fun DayChoice(
    days: List<PlanDayOption>,
    selected: Int?,
    onDayChange: (Int?) -> Unit,
    testTag: String,
    allowNone: Boolean = true,
) {
    var expanded by remember { mutableStateOf(false) }
    val none = stringResource(R.string.add_meal_day_none)
    val selectedLabel = days.firstOrNull { it.dayIndex == selected }?.let { dayLabel(it) } ?: none

    Box(modifier = Modifier.fillMaxWidth()) {
        OutlinedTextField(
            value = selectedLabel,
            onValueChange = {},
            readOnly = true,
            label = { Text(stringResource(R.string.add_meal_day_label)) },
            trailingIcon = { Icon(Icons.Default.ArrowDropDown, contentDescription = null) },
            modifier = Modifier
                .fillMaxWidth()
                .testTag(testTag),
        )
        Box(
            modifier = Modifier
                .matchParentSize()
                .clickable(role = Role.DropdownList) { expanded = true }
                .semantics { contentDescription = selectedLabel },
        )
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            if (allowNone) {
                DropdownMenuItem(
                    text = { Text(none) },
                    onClick = {
                        expanded = false
                        onDayChange(null)
                    },
                )
            }
            days.forEach { day ->
                DropdownMenuItem(
                    text = { Text(dayLabel(day)) },
                    onClick = {
                        expanded = false
                        onDayChange(day.dayIndex)
                    },
                )
            }
        }
    }
}

@Composable
private fun dayLabel(day: PlanDayOption): String =
    "${stringResource(R.string.plan_detail_day_title, day.dayIndex + 1)} · ${formatPlanDay(day.date)}"