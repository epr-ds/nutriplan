package com.nutriplan.shared.data.local

import com.nutriplan.shared.data.model.UpdateMealRequest
import com.nutriplan.shared.testing.meal
import com.nutriplan.shared.testing.newDatabase
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PendingChangeStoreTest {

    private val database = newDatabase()
    private val store = PendingChangeStore(database)

    private val m1 = meal("m1", dayIndex = 0, type = "lunch")
    private val m2 = meal("m2", dayIndex = 1, type = "dinner")

    @Test
    fun `an empty store has nothing waiting`() {
        assertTrue(store.waiting().isEmpty())
        assertTrue(store.failed().isEmpty())
    }

    @Test
    fun `an edit is stored with only the fields that were changed`() {
        val change = store.queueUpdate("p1", m1, UpdateMealRequest(servings = 3.0))

        assertEquals(ChangeKind.UPDATE, change.kind)
        assertEquals(3.0, change.servings)
        assertNull(change.dayIndex)
        assertNull(change.satisfactionLevel)
        assertEquals("lunch", change.mealType)
        assertEquals(UpdateMealRequest(servings = 3.0), store.waiting().single().toRequest())
    }

    @Test
    fun `a removal is stored for the meal`() {
        val change = store.queueRemove("p1", m1)

        assertEquals(ChangeKind.REMOVE, change.kind)
        assertEquals("m1", change.mealId)
        assertEquals(listOf(change.id), store.waiting().map { it.id })
    }

    @Test
    fun `a second edit of the same meal merges into the waiting one, the last write winning`() {
        val first = store.queueUpdate("p1", m1, UpdateMealRequest(servings = 2.0, dayIndex = 1))

        val second = store.queueUpdate("p1", m1, UpdateMealRequest(servings = 4.0, satisfactionLevel = 5))

        assertEquals(first.id, second.id, "still one row")
        val stored = store.waiting().single()
        assertEquals(4.0, stored.servings)
        assertEquals(1, stored.dayIndex)
        assertEquals(5, stored.satisfactionLevel)
    }

    @Test
    fun `edits of different meals are separate rows, oldest first`() {
        val a = store.queueUpdate("p1", m1, UpdateMealRequest(servings = 2.0))
        val b = store.queueUpdate("p1", m2, UpdateMealRequest(servings = 3.0))

        assertEquals(listOf(a.id, b.id), store.waiting().map { it.id })
    }

    @Test
    fun `a removal replaces the edits waiting for that meal`() {
        store.queueUpdate("p1", m1, UpdateMealRequest(servings = 2.0))
        store.queueUpdate("p1", m2, UpdateMealRequest(servings = 3.0))

        store.queueRemove("p1", m1)

        val waiting = store.waiting()
        assertEquals(2, waiting.size)
        assertEquals(setOf(ChangeKind.UPDATE, ChangeKind.REMOVE), waiting.map { it.kind }.toSet())
        assertEquals("m1", waiting.single { it.kind == ChangeKind.REMOVE }.mealId)
        assertEquals("m2", waiting.single { it.kind == ChangeKind.UPDATE }.mealId)
    }

    @Test
    fun `an edit of a meal already queued for removal changes nothing`() {
        val removal = store.queueRemove("p1", m1)

        val result = store.queueUpdate("p1", m1, UpdateMealRequest(servings = 9.0))

        assertEquals(removal.id, result.id)
        assertEquals(ChangeKind.REMOVE, result.kind)
        assertEquals(1, store.waiting().size)
    }

    @Test
    fun `removing twice leaves one removal`() {
        store.queueRemove("p1", m1)
        store.queueRemove("p1", m1)

        assertEquals(1, store.waiting().size)
    }

    @Test
    fun `a plan only sees its own waiting changes`() {
        store.queueUpdate("p1", m1, UpdateMealRequest(servings = 2.0))
        store.queueUpdate("p2", m2, UpdateMealRequest(servings = 2.0))

        assertEquals(listOf("m1"), store.waitingFor("p1").map { it.mealId })
    }

    @Test
    fun `the same meal id in two plans is not mixed up`() {
        store.queueUpdate("p1", m1, UpdateMealRequest(servings = 2.0))
        store.queueUpdate("p2", m1, UpdateMealRequest(servings = 5.0))

        assertEquals(2, store.waiting().size)
        assertEquals(2.0, store.waitingFor("p1").single().servings)
    }

    @Test
    fun `attempts are counted`() {
        val change = store.queueRemove("p1", m1)

        store.bumpAttempts(change.id)

        assertEquals(1, store.waiting().single().attempts)
    }

    @Test
    fun `a failed change leaves the queue and keeps its reason`() {
        val change = store.queueUpdate("p1", m1, UpdateMealRequest(dayIndex = 99))

        store.markFailed(change.id, PendingFailure.REJECTED)

        assertTrue(store.waiting().isEmpty())
        assertEquals(PendingFailure.REJECTED, store.failed().single().failure)
    }

    @Test
    fun `after a failure a new edit starts a fresh change`() {
        val failed = store.queueUpdate("p1", m1, UpdateMealRequest(dayIndex = 99))
        store.markFailed(failed.id, PendingFailure.REJECTED)

        val fresh = store.queueUpdate("p1", m1, UpdateMealRequest(servings = 2.0))

        assertTrue(fresh.id != failed.id)
        assertEquals(1, store.waiting().size)
        assertEquals(1, store.failed().size)
    }

    @Test
    fun `remove and clear forget changes`() {
        val a = store.queueRemove("p1", m1)
        store.queueRemove("p1", m2)

        store.remove(a.id)
        assertEquals(1, store.waiting().size)

        store.clear()
        assertTrue(store.waiting().isEmpty())
    }

    @Test
    fun `the queue survives the app restarting`() {
        store.queueRemove("p1", m1)

        assertEquals(listOf("m1"), PendingChangeStore(database).waiting().map { it.mealId })
    }

    // --- showing a change on a meal ---

    @Test
    fun `an edit changes only the fields it carries and marks the meal as waiting`() {
        val edit = store.queueUpdate("p1", m1, UpdateMealRequest(dayIndex = 4))

        val shown = edit.applyTo(m1)

        assertEquals(4, shown.dayIndex)
        assertEquals(m1.servings, shown.servings)
        assertEquals(m1.satisfactionLevel, shown.satisfactionLevel)
        assertEquals(m1.nutritionalInfo, shown.nutritionalInfo, "no new servings, no new nutrition")
        assertTrue(shown.syncPending)
        assertFalse(m1.syncPending)
    }

    @Test
    fun `a removal leaves the meal as it is, hiding it is the plan's job`() {
        val removal = store.queueRemove("p1", m1)

        assertEquals(m1, removal.applyTo(m1))
    }

    @Test
    fun `a change type written by a newer app reads as an edit`() {
        val change = store.queueUpdate("p1", m1, UpdateMealRequest(servings = 2.0))
        database.pendingChangeQueries.deleteById(change.id)
        database.pendingChangeQueries.insertChange("p1", "m1", "lunch", "SOMETHING_NEW", 2.0, null, null)

        assertEquals(ChangeKind.UPDATE, store.waiting().single().kind)
    }
}
