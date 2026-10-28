package com.nutriplan.shared.notifications

import com.nutriplan.shared.data.model.NotificationPreferences
import java.time.LocalTime
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * NTF-803: the quiet-hours window of the notification preferences is evaluated the same way on
 * every platform, including overnight windows that wrap past midnight.
 */
class NotificationQuietHoursTest {

    private fun preferences(start: String?, end: String?): NotificationPreferences =
        NotificationPreferences(
            pushEnabled = true,
            emailEnabled = true,
            mealReminders = true,
            orderUpdates = true,
            promotions = true,
            quietHoursStart = start,
            quietHoursEnd = end,
        )

    @Test
    fun `no quiet hours means notifications are never quiet`() {
        assertFalse(preferences(start = null, end = null).isQuietHours(now = LocalTime.NOON))
    }

    @Test
    fun `quiet hours cover the configured window`() {
        val prefs = preferences(start = "09:00", end = "17:00")

        assertTrue(prefs.isQuietHours(now = LocalTime.of(12, 0)))
    }

    @Test
    fun `a quiet hours window that wraps past midnight covers the late evening`() {
        val prefs = preferences(start = "22:00", end = "06:00")

        assertTrue(prefs.isQuietHours(now = LocalTime.of(23, 0)))
        assertTrue(prefs.isQuietHours(now = LocalTime.of(2, 0)))
        assertFalse(prefs.isQuietHours(now = LocalTime.of(12, 0)))
    }
}
