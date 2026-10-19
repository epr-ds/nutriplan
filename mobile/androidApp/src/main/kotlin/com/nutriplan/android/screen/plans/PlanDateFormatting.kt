package com.nutriplan.android.screen.plans

import com.nutriplan.shared.planning.IsoDate
import java.text.DateFormat
import java.text.ParseException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * Formats a server date (`yyyy-MM-dd`, optionally followed by a time) for display in [locale], for
 * example "Thursday, October 1, 2026". Both steps use UTC so the day never shifts with the device's
 * time zone. Anything that does not parse is returned unchanged rather than hidden.
 *
 * (`java.time` needs API 26 and the app supports API 24.)
 */
internal fun formatPlanDay(isoDate: String, locale: Locale = Locale.getDefault()): String {
    val parser = SimpleDateFormat("yyyy-MM-dd", Locale.US).apply {
        isLenient = false
        timeZone = TimeZone.getTimeZone("UTC")
    }
    val date = try {
        parser.parse(isoDate.take(ISO_DATE_LENGTH))
    } catch (e: ParseException) {
        null
    } ?: return isoDate
    return DateFormat.getDateInstance(DateFormat.FULL, locale)
        .apply { timeZone = TimeZone.getTimeZone("UTC") }
        .format(date)
}

private const val ISO_DATE_LENGTH = 10
private const val MILLIS_PER_DAY = 86_400_000L

/**
 * The value Material's date picker uses for an ISO date: midnight UTC of that day in milliseconds.
 * Null if [isoDate] is not a valid date.
 */
internal fun isoToPickerMillis(isoDate: String): Long? = IsoDate.toEpochDay(isoDate)?.let { it * MILLIS_PER_DAY }

/** The ISO date of a date picker selection (midnight UTC milliseconds); no time zone can shift it. */
internal fun pickerMillisToIso(millis: Long): String = IsoDate.fromEpochDay(millis.floorDiv(MILLIS_PER_DAY))

/** Today's date on the device (its local time zone) as an ISO date. */
internal fun todayIso(now: Date = Date(), zone: TimeZone = TimeZone.getDefault()): String =
    SimpleDateFormat("yyyy-MM-dd", Locale.US).apply { timeZone = zone }.format(now)
