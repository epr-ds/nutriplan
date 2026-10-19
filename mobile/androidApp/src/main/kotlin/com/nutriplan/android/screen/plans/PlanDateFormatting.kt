package com.nutriplan.android.screen.plans

import java.text.DateFormat
import java.text.ParseException
import java.text.SimpleDateFormat
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
