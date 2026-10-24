package com.nutriplan.shared.notifications

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * NTF-504: the notification permission state enum used by both platforms' priming flow.
 */
class PushPermissionStatusTest {

    @Test
    fun `the permission state covers every answer the OS can give`() {
        assertEquals(4, PushPermissionStatus.values().size)
    }

    @Test
    fun `granted is the only state that allows notifications`() {
        assertEquals(PushPermissionStatus.GRANTED, PushPermissionStatus.GRANTED)
        assertEquals(false, PushPermissionStatus.NOT_ASKED.isGrantedOrProvisional)
        assertEquals(true, PushPermissionStatus.GRANTED.isGrantedOrProvisional)
        assertEquals(false, PushPermissionStatus.DENIED.isGrantedOrProvisional)
        assertEquals(true, PushPermissionStatus.PROVISIONAL.isGrantedOrProvisional)
    }
}