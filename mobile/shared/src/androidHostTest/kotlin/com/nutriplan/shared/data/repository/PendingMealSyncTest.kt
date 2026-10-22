package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.local.PendingFailure
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.testing.QueueFixture
import com.nutriplan.shared.testing.addRequest
import com.nutriplan.shared.testing.fullPlan
import com.nutriplan.shared.testing.meal
import com.nutriplan.shared.testing.queuedRecipe
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PendingMealSyncTest {

    private val fixture = QueueFixture()
    private val sync = fixture.sync
    private val remote = fixture.remote
    private val store = fixture.store

    private fun queue(recipeId: String = "r1", day: Int? = null, servings: Double = 2.0, plan: String = "p1") =
        sync.queueAdd(plan, addRequest(recipeId = recipeId, servings = servings), day, queuedRecipe(recipeId))

    // --- queueing ---

    @Test
    fun `queueing stores the request at once and shows it as waiting`() {
        queue()

        assertTrue(sync.hasWaiting())
        assertEquals(1, store.shownFor("p1").size)
        assertTrue(remote.added.isEmpty(), "nothing is sent by queueing")
    }

    @Test
    fun `the waiting meal carries the recipe and its nutrition for the servings`() {
        val pending = queue(servings = 2.0)

        assertEquals("Recipe r1", pending.recipe.name)
        assertEquals("https://images.example/r1.jpg", pending.recipe.imageUrl)
        // 300 kcal per serving x 2 servings.
        assertEquals(600, pending.nutritionalInfo?.calories)
        assertEquals(40.0, pending.nutritionalInfo?.protein)
        assertEquals(10.0, pending.nutritionalInfo?.sugar)
    }

    @Test
    fun `a recipe without nutrition queues without it`() {
        val pending = sync.queueAdd("p1", addRequest(), null, queuedRecipe().copy(nutritionalInfo = null))

        assertNull(pending.nutritionalInfo)
    }

    // --- flushing ---

    @Test
    fun `flushing an empty queue does nothing`() = runTest {
        val result = sync.flush()

        assertEquals(FlushResult(added = 0, failed = 0, waiting = 0), result)
        assertTrue(remote.added.isEmpty())
    }

    @Test
    fun `flush sends the queued meals oldest first and empties the queue`() = runTest {
        queue("a")
        queue("b")

        val result = sync.flush()

        assertEquals(FlushResult(added = 2, failed = 0, waiting = 0), result)
        assertEquals(listOf("a", "b"), remote.added.map { it.second.recipeId })
        assertFalse(sync.hasWaiting())
    }

    @Test
    fun `flush sends the request that was queued`() = runTest {
        sync.queueAdd("p9", addRequest(recipeId = "r5", mealType = "dinner", servings = 1.5), null, queuedRecipe("r5"))

        sync.flush()

        assertEquals("p9" to addRequest(recipeId = "r5", mealType = "dinner", servings = 1.5), remote.added.single())
    }

    @Test
    fun `a queued day is set after the meal is created`() = runTest {
        queue(day = 3)

        sync.flush()

        val (plan, mealId, request) = remote.updated.single()
        assertEquals("p1", plan)
        assertEquals("srv-meal-1", mealId)
        assertEquals(3, request.dayIndex)
    }

    @Test
    fun `no day means no second request`() = runTest {
        queue(day = null)

        sync.flush()

        assertTrue(remote.updated.isEmpty())
    }

    @Test
    fun `a sent meal makes the saved plan stale`() = runTest {
        fixture.cache.upsertPlan(fullPlan("p1", meals = listOf(meal("m1"))))
        queue()

        sync.flush()

        assertNull(fixture.cache.getPlan("p1"), "its saved detail is dropped so the next read refills it")
    }

    // --- when the server cannot be reached ---

    @Test
    fun `offline keeps the meal queued and stops, so later meals keep their order`() = runTest {
        queue("a")
        queue("b")
        remote.addFailures = mutableListOf(ApiException.NetworkError())

        val result = sync.flush()

        assertEquals(FlushResult(added = 0, failed = 0, waiting = 2), result)
        assertEquals(listOf("a"), remote.added.map { it.second.recipeId }, "b was not even tried")
        assertEquals(listOf("a", "b"), store.waiting().map { it.recipeId })
        assertEquals(1, store.waiting().first().attempts)
        assertEquals(0, store.waiting().last().attempts)
    }

    @Test
    fun `a server error is treated like being offline`() = runTest {
        queue()
        remote.addFailures = mutableListOf(ApiException.HttpError(503, null))

        val result = sync.flush()

        assertEquals(1, result.waiting)
        assertTrue(store.failed().isEmpty())
    }

    @Test
    fun `an ended session is not the meal's fault, so it stays queued`() = runTest {
        queue()
        remote.addFailures = mutableListOf(ApiException.HttpError(401, null))

        val result = sync.flush()

        assertEquals(1, result.waiting)
        assertTrue(store.failed().isEmpty())
    }

    @Test
    fun `the next flush sends what was waiting`() = runTest {
        queue("a")
        remote.addFailures = mutableListOf(ApiException.NetworkError())
        sync.flush()

        val result = sync.flush()

        assertEquals(FlushResult(added = 1, failed = 0, waiting = 0), result)
        assertFalse(sync.hasWaiting())
    }

    // --- when the server refuses it ---

    @Test
    fun `a refused meal is rolled back, gone from the plan and kept as a failure`() = runTest {
        val pending = queue()
        remote.addFailures = mutableListOf(ApiException.HttpError(422, null))

        val result = sync.flush()

        assertEquals(FlushResult(added = 0, failed = 1, waiting = 0), result)
        assertTrue(store.shownFor("p1").isEmpty(), "the stand-in leaves the plan")
        assertEquals(PendingFailure.REJECTED, sync.failures().single().failure)
        assertEquals(pending.id, sync.failures().single().id)
    }

    @Test
    fun `a missing plan or recipe is a not found failure`() = runTest {
        queue()
        remote.addFailures = mutableListOf(ApiException.HttpError(404, null))

        sync.flush()

        assertEquals(PendingFailure.NOT_FOUND, sync.failures().single().failure)
    }

    @Test
    fun `anything else the server answers is an unknown failure`() = runTest {
        queue()
        remote.addFailures = mutableListOf(ApiException.HttpError(418, null))

        sync.flush()

        assertEquals(PendingFailure.UNKNOWN, sync.failures().single().failure)
    }

    @Test
    fun `a refused meal does not hold back the ones after it`() = runTest {
        queue("bad")
        queue("good")
        remote.addFailures = mutableListOf(ApiException.HttpError(422, null))

        val result = sync.flush()

        assertEquals(FlushResult(added = 1, failed = 1, waiting = 0), result)
        assertEquals(listOf("bad", "good"), remote.added.map { it.second.recipeId })
    }

    @Test
    fun `failures can be listed for one plan and dismissed`() = runTest {
        queue(plan = "p1")
        queue(plan = "p2")
        remote.addFailures = mutableListOf(ApiException.HttpError(422, null), ApiException.HttpError(422, null))
        sync.flush()

        assertEquals(2, sync.failures().size)
        val mine = sync.failures("p1").single()
        sync.dismissFailure(mine.id)

        assertTrue(sync.failures("p1").isEmpty())
        assertEquals(1, sync.failures().size)
    }

    // --- a meal created whose day could not be set ---

    @Test
    fun `if only the day fails the meal is remembered and never added twice`() = runTest {
        queue(day = 2)
        remote.updateFailure = ApiException.NetworkError()

        val first = sync.flush()

        assertEquals(1, first.waiting)
        assertEquals("srv-meal-1", store.waiting().single().remoteMealId)
        assertTrue(store.shownFor("p1").isEmpty(), "the real meal is on the server now")

        remote.updateFailure = null
        val second = sync.flush()

        assertEquals(FlushResult(added = 1, failed = 0, waiting = 0), second)
        assertEquals(1, remote.added.size, "the meal was created once")
        assertEquals(2, remote.updated.size)
        assertEquals("srv-meal-1", remote.updated.last().second)
    }

    // --- two flushes at once ---

    @Test
    fun `two flushes at the same time never send a meal twice`() = runTest {
        queue()
        val gate = CompletableDeferred<Unit>()
        remote.gate = gate

        val first = async { sync.flush() }
        testScheduler.advanceUntilIdle()
        val second = async { sync.flush() }
        testScheduler.advanceUntilIdle()
        gate.complete(Unit)

        first.await()
        val secondResult = second.await()

        assertEquals(1, remote.added.size)
        assertEquals(FlushResult(added = 0, failed = 0, waiting = 0), secondResult, "the queue was already empty")
        assertNotNull(first)
    }
}
