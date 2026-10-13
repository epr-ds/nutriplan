package com.nutriplan.shared.navigation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PendingDeepLinkTest {

    private val pending = PendingDeepLink()

    @Test
    fun `accepted link is released when authenticated and then cleared`() {
        assertTrue(pending.offer("nutriplan://meal/m1"))

        assertEquals(Route.DeepLinkMeal("m1"), pending.takeIfAuthenticated(true))
        assertNull(pending.takeIfAuthenticated(true))
        assertFalse(pending.hasPending)
    }

    @Test
    fun `link is held while unauthenticated and released after login`() {
        pending.offer("nutriplan://plan/p1/manage")

        assertNull(pending.takeIfAuthenticated(false))
        assertTrue(pending.hasPending)
        assertEquals(Route.DeepLinkPlan("p1", "manage"), pending.takeIfAuthenticated(true))
    }

    @Test
    fun `flows that must not be opened from outside are rejected`() {
        listOf(
            "nutriplan://splash",
            "nutriplan://onboarding",
            "nutriplan://auth",
            "nutriplan://main",
            "nutriplan://checkout",
            "nutriplan://profile/edit",
            "nutriplan://profile/dietary",
            "nutriplan://meal-plan/new",
        ).forEach { link ->
            assertFalse(pending.offer(link), "should reject $link")
        }
        assertFalse(pending.hasPending)
    }

    @Test
    fun `detail screens can be opened from outside`() {
        listOf(
            "nutriplan://meal/m1",
            "nutriplan://plan/p1",
            "nutriplan://plan/p1/renew",
            "nutriplan://order/o1",
            "nutriplan://recipe/r1",
            "nutriplan://meal-plan/p1",
            "nutriplan://notifications",
        ).forEach { link ->
            assertTrue(pending.offer(link), "should accept $link")
        }
    }

    @Test
    fun `null empty and foreign links are rejected`() {
        assertFalse(pending.offer(null))
        assertFalse(pending.offer(""))
        assertFalse(pending.offer("https://example.com/meal/m1"))
        assertFalse(pending.offer("nutriplan://unknown"))
    }

    @Test
    fun `newer accepted link replaces older one`() {
        pending.offer("nutriplan://meal/old")
        pending.offer("nutriplan://meal/new")

        assertEquals(Route.DeepLinkMeal("new"), pending.takeIfAuthenticated(true))
    }

    @Test
    fun `rejected link does not clear a pending one`() {
        pending.offer("nutriplan://meal/m1")
        assertFalse(pending.offer("nutriplan://checkout"))

        assertEquals(Route.DeepLinkMeal("m1"), pending.takeIfAuthenticated(true))
    }

    @Test
    fun `clear drops the pending link`() {
        pending.offer("nutriplan://meal/m1")
        pending.clear()

        assertNull(pending.takeIfAuthenticated(true))
    }
}
