package com.nutriplan.shared.planning

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PlanDaysTest {

    @Test
    fun `lists every day of an inclusive range with its 0-based index`() {
        assertEquals(
            listOf(PlanDayOption(0, "2026-10-01"), PlanDayOption(1, "2026-10-02")),
            planDays("2026-10-01", "2026-10-02"),
        )
    }

    @Test
    fun `a single day plan has one day`() {
        assertEquals(listOf(PlanDayOption(0, "2026-10-01")), planDays("2026-10-01", "2026-10-01"))
    }

    @Test
    fun `crosses month and leap-year boundaries`() {
        assertEquals(
            listOf("2028-02-28", "2028-02-29", "2028-03-01"),
            planDays("2028-02-28", "2028-03-01").map { it.date },
        )
    }

    @Test
    fun `a backwards range or an invalid date has no days`() {
        assertTrue(planDays("2026-10-05", "2026-10-01").isEmpty())
        assertTrue(planDays("not-a-date", "2026-10-01").isEmpty())
        assertTrue(planDays("2026-10-01", "2026-13-01").isEmpty())
    }

    @Test
    fun `a very long range is capped`() {
        assertEquals(366, planDays("2026-01-01", "2030-01-01").size)
    }
}
