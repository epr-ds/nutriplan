package com.nutriplan.shared.planning

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class IsoDateTest {

    @Test
    fun `the epoch is day zero`() {
        assertEquals(0L, IsoDate.toEpochDay("1970-01-01"))
        assertEquals("1970-01-01", IsoDate.fromEpochDay(0))
        assertEquals(1L, IsoDate.toEpochDay("1970-01-02"))
        assertEquals(-1L, IsoDate.toEpochDay("1969-12-31"))
    }

    @Test
    fun `known dates map to known epoch days`() {
        assertEquals(10957L, IsoDate.toEpochDay("2000-01-01"))
        assertEquals(20_727L, IsoDate.toEpochDay("2026-10-01"))
    }

    @Test
    fun `epoch days and dates round trip across every year from 0000 to 9999`() {
        // -719_528 is 0000-01-01 and 2_932_896 is 9999-12-31, the limits of the four-digit format.
        for (day in -719_528L..2_932_896L step 997L) {
            assertEquals(day, IsoDate.toEpochDay(IsoDate.fromEpochDay(day)), "day $day")
        }
        assertEquals("0000-01-01", IsoDate.fromEpochDay(-719_528L))
        assertEquals("9999-12-31", IsoDate.fromEpochDay(2_932_896L))
    }

    @Test
    fun `adding days crosses month and year ends`() {
        assertEquals("2026-10-07", IsoDate.addDays("2026-10-01", 6))
        assertEquals("2026-11-01", IsoDate.addDays("2026-10-31", 1))
        assertEquals("2027-01-01", IsoDate.addDays("2026-12-31", 1))
        assertEquals("2026-09-30", IsoDate.addDays("2026-10-01", -1))
        assertEquals("2026-10-01", IsoDate.addDays("2026-10-01", 0))
    }

    @Test
    fun `leap years follow the gregorian rules`() {
        assertEquals("2024-02-29", IsoDate.addDays("2024-02-28", 1))
        assertEquals("2024-03-01", IsoDate.addDays("2024-02-29", 1))
        assertEquals("2025-03-01", IsoDate.addDays("2025-02-28", 1))
        assertEquals("2100-03-01", IsoDate.addDays("2100-02-28", 1)) // divisible by 100: not leap
        assertEquals("2000-02-29", IsoDate.addDays("2000-02-28", 1)) // divisible by 400: leap
    }

    @Test
    fun `days between counts in both directions`() {
        assertEquals(6, IsoDate.daysBetween("2026-10-01", "2026-10-07"))
        assertEquals(0, IsoDate.daysBetween("2026-10-01", "2026-10-01"))
        assertEquals(-6, IsoDate.daysBetween("2026-10-07", "2026-10-01"))
        assertEquals(366, IsoDate.daysBetween("2024-01-01", "2025-01-01"))
    }

    @Test
    fun `only real dates in the exact format are valid`() {
        assertTrue(IsoDate.isValid("2026-10-01"))
        assertTrue(IsoDate.isValid("2024-02-29"))
        assertFalse(IsoDate.isValid("2025-02-29"))
        assertFalse(IsoDate.isValid("2100-02-29"))
        assertFalse(IsoDate.isValid("2026-13-01"))
        assertFalse(IsoDate.isValid("2026-00-10"))
        assertFalse(IsoDate.isValid("2026-04-31"))
        assertFalse(IsoDate.isValid("2026-10-00"))
        assertFalse(IsoDate.isValid("2026-1-1"))
        assertFalse(IsoDate.isValid("26-10-01"))
        assertFalse(IsoDate.isValid("2026-10-01T00:00:00Z"))
        assertFalse(IsoDate.isValid(""))
        assertFalse(IsoDate.isValid("soon"))
    }

    @Test
    fun `invalid input gives null instead of throwing`() {
        assertNull(IsoDate.addDays("nope", 1))
        assertNull(IsoDate.daysBetween("2026-10-01", "nope"))
        assertNull(IsoDate.daysBetween("nope", "2026-10-01"))
    }
}
