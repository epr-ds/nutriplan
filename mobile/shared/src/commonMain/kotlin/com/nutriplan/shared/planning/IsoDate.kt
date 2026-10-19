package com.nutriplan.shared.planning

/**
 * Calendar arithmetic on ISO dates (`yyyy-MM-dd`) without a date library.
 *
 * The API sends plan dates as ISO strings and places a meal by its 0-based day index within the
 * plan's range, so the app needs to add days to a date and compare dates. The proleptic Gregorian
 * calendar (days-from-civil, after H. Hinnant) makes that exact, including leap years.
 */
object IsoDate {

    private val PATTERN = Regex("""^(\d{4})-(\d{2})-(\d{2})$""")

    /** True when [iso] is a real calendar date written as `yyyy-MM-dd`. */
    fun isValid(iso: String): Boolean = toEpochDay(iso) != null

    /** Days since 1970-01-01 for [iso], or null if it is not a valid date. */
    fun toEpochDay(iso: String): Long? {
        val parts = PATTERN.matchEntire(iso)?.destructured ?: return null
        val (year, month, day) = parts.toList().map { it.toInt() }
        if (month !in 1..MONTHS || day !in 1..daysInMonth(year, month)) return null
        return daysFromCivil(year, month, day)
    }

    /** The ISO date [epochDay] days after 1970-01-01. */
    fun fromEpochDay(epochDay: Long): String {
        val z = epochDay + EPOCH_SHIFT
        val era = (if (z >= 0) z else z - (DAYS_PER_ERA - 1)) / DAYS_PER_ERA
        val dayOfEra = z - era * DAYS_PER_ERA
        val yearOfEra = (dayOfEra - dayOfEra / 1460 + dayOfEra / 36524 - dayOfEra / 146096) / 365
        val dayOfYear = dayOfEra - (365 * yearOfEra + yearOfEra / 4 - yearOfEra / 100)
        val monthPart = (5 * dayOfYear + 2) / 153
        val day = dayOfYear - (153 * monthPart + 2) / 5 + 1
        val month = if (monthPart < 10) monthPart + 3 else monthPart - 9
        val year = yearOfEra + era * 400 + if (month <= 2) 1 else 0
        return "${year.toString().padStart(4, '0')}-${month.toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}"
    }

    /** [iso] plus [days] days (negative goes back), or null if [iso] is not a valid date. */
    fun addDays(iso: String, days: Int): String? = toEpochDay(iso)?.let { fromEpochDay(it + days) }

    /** Whole days from [from] to [to] (negative if [to] is earlier), or null if either is invalid. */
    fun daysBetween(from: String, to: String): Int? {
        val start = toEpochDay(from) ?: return null
        val end = toEpochDay(to) ?: return null
        return (end - start).toInt()
    }

    private fun daysInMonth(year: Int, month: Int): Int = when (month) {
        2 -> if (isLeapYear(year)) 29 else 28
        4, 6, 9, 11 -> 30
        else -> 31
    }

    private fun isLeapYear(year: Int): Boolean = (year % 4 == 0 && year % 100 != 0) || year % 400 == 0

    private fun daysFromCivil(year: Int, month: Int, day: Int): Long {
        val y = (if (month <= 2) year - 1 else year).toLong()
        val era = (if (y >= 0) y else y - 399) / 400
        val yearOfEra = y - era * 400
        val monthShifted = if (month > 2) month - 3 else month + 9
        val dayOfYear = (153 * monthShifted + 2) / 5 + day - 1
        val dayOfEra = yearOfEra * 365 + yearOfEra / 4 - yearOfEra / 100 + dayOfYear
        return era * DAYS_PER_ERA + dayOfEra - EPOCH_SHIFT
    }

    private const val MONTHS = 12
    private const val DAYS_PER_ERA = 146_097L
    private const val EPOCH_SHIFT = 719_468L
}
