package com.nutriplan.android.plans

import com.nutriplan.android.screen.plans.formatPlanDay
import com.nutriplan.android.screen.plans.isoToPickerMillis
import com.nutriplan.android.screen.plans.pickerMillisToIso
import com.nutriplan.android.screen.plans.todayIso
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.Locale
import java.util.TimeZone

/** DPL-505: plan dates are shown in the user's language and never shift with the time zone. */
class PlanDateFormattingTest {

    private lateinit var originalZone: TimeZone

    @Before
    fun saveZone() {
        originalZone = TimeZone.getDefault()
    }

    @After
    fun restoreZone() = TimeZone.setDefault(originalZone)

    @Test
    fun `formats a server date for the given language`() {
        assertEquals("Thursday, October 1, 2026", formatPlanDay("2026-10-01", Locale.US))
        assertTrue(formatPlanDay("2026-10-01", Locale("es", "ES")).contains("octubre"))
    }

    @Test
    fun `ignores a time suffix`() {
        assertEquals("Thursday, October 1, 2026", formatPlanDay("2026-10-01T23:30:00Z", Locale.US))
    }

    @Test
    fun `the day does not shift with the device time zone`() {
        for (zone in listOf("Pacific/Kiritimati", "America/Los_Angeles", "UTC", "Pacific/Pago_Pago")) {
            TimeZone.setDefault(TimeZone.getTimeZone(zone))
            assertEquals("zone $zone", "Thursday, October 1, 2026", formatPlanDay("2026-10-01", Locale.US))
        }
    }

    @Test
    fun `the date picker value for a day is midnight UTC of that day`() {
        assertEquals(1_790_812_800_000L, isoToPickerMillis("2026-10-01"))
        assertEquals(0L, isoToPickerMillis("1970-01-01"))
        assertNull(isoToPickerMillis("not a date"))
    }

    @Test
    fun `a date picker selection maps back to the same day, whatever the time zone`() {
        for (zone in listOf("Pacific/Kiritimati", "America/Los_Angeles", "UTC", "Pacific/Pago_Pago")) {
            TimeZone.setDefault(TimeZone.getTimeZone(zone))
            assertEquals("zone $zone", "2026-10-01", pickerMillisToIso(1_790_812_800_000L))
            // Anywhere inside the same UTC day is still that day.
            assertEquals("zone $zone", "2026-10-01", pickerMillisToIso(1_790_812_800_000L + 86_399_999L))
            assertEquals("zone $zone", "2026-09-30", pickerMillisToIso(1_790_812_800_000L - 1L))
        }
    }

    @Test
    fun `a date round trips through the date picker value`() {
        for (iso in listOf("2024-02-29", "2026-12-31", "2000-01-01", "1999-12-31")) {
            assertEquals(iso, pickerMillisToIso(isoToPickerMillis(iso)!!))
        }
    }

    @Test
    fun `today is the device's local date, not UTC's`() {
        // 2026-10-01 23:30 UTC is already Oct 2 in Kiritimati (UTC+14) and still Oct 1 in Los Angeles.
        val instant = java.util.Date(1_790_812_800_000L + 23 * 3_600_000L + 30 * 60_000L)

        assertEquals("2026-10-02", todayIso(instant, TimeZone.getTimeZone("Pacific/Kiritimati")))
        assertEquals("2026-10-01", todayIso(instant, TimeZone.getTimeZone("America/Los_Angeles")))
        assertEquals("2026-10-01", todayIso(instant, TimeZone.getTimeZone("UTC")))
    }

    @Test
    fun `something that is not a date is returned unchanged`() {
        assertEquals("soon", formatPlanDay("soon", Locale.US))
        assertEquals("2026-13-45", formatPlanDay("2026-13-45", Locale.US))
        assertEquals("", formatPlanDay("", Locale.US))
    }
}
