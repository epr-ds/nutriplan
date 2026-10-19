package com.nutriplan.android.plans

import com.nutriplan.android.screen.plans.formatPlanDay
import org.junit.After
import org.junit.Assert.assertEquals
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
    fun `something that is not a date is returned unchanged`() {
        assertEquals("soon", formatPlanDay("soon", Locale.US))
        assertEquals("2026-13-45", formatPlanDay("2026-13-45", Locale.US))
        assertEquals("", formatPlanDay("", Locale.US))
    }
}
