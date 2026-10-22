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

    // --- background sync (DPL-407 follow-up) ---

    @Test
    fun `queueing a meal asks the platform for a background sync`() {
        queue()

        assertEquals(1, fixture.scheduler.requests)
    }

    @Test
    fun `every queued meal asks again, which is harmless because requests are merged`() {
        queue("a")
        queue("b")

        assertEquals(2, fixture.scheduler.requests)
    }

    @Test
    fun `flushing and reading the queue do not ask for a sync`() = runTest {
        queue()
        val asked = fixture.scheduler.requests

        sync.flush()
        sync.hasWaiting()
        sync.failures()

        assertEquals(asked, fixture.scheduler.requests)
    }

    @Test
    fun `an explicit request is passed on, for example when the app starts`() {
        sync.requestSync()

        assertEquals(1, fixture.scheduler.requests)
    }

    @Test
    fun `without a platform scheduler queueing still works`() {
        val plain = PendingMealSync(remote, store, fixture.cache)

        plain.queueAdd("p1", addRequest(), null, queuedRecipe())
        plain.requestSync()

        assertTrue(plain.hasWaiting())
    }

    @Test
    fun `the sync can be driven through the flusher interface the background job uses`() = runTest {
        queue()
        val flusher: MealQueueFlusher = sync

        val result = flusher.flush()

        assertEquals(1, result.added)
    }

    // --- queued edits and removals ---

    private val serverMeal = com.nutriplan.shared.testing.meal("m1", dayIndex = 0)

    @Test
    fun `a queued edit is sent as a partial update and forgotten`() = runTest {
        sync.queueUpdate("p1", serverMeal, com.nutriplan.shared.data.model.UpdateMealRequest(servings = 3.0, satisfactionLevel = 5))

        val result = sync.flush()

        assertEquals(FlushResult(added = 1, failed = 0, waiting = 0), result)
        val (plan, meal, request) = remote.updated.single()
        assertEquals("p1", plan)
        assertEquals("m1", meal)
        assertEquals(com.nutriplan.shared.data.model.UpdateMealRequest(servings = 3.0, satisfactionLevel = 5), request)
        assertFalse(sync.hasWaiting())
    }

    @Test
    fun `a queued removal is sent and forgotten`() = runTest {
        sync.queueRemove("p1", serverMeal)

        sync.flush()

        assertEquals(listOf("p1" to "m1"), remote.removed)
        assertFalse(sync.hasWaiting())
    }

    @Test
    fun `queueing a change asks for a background sync and reports it is waiting`() {
        sync.queueUpdate("p1", serverMeal, com.nutriplan.shared.data.model.UpdateMealRequest(servings = 2.0))

        assertEquals(1, fixture.scheduler.requests)
        assertTrue(sync.hasWaiting())
    }

    @Test
    fun `new meals go first, then the changes`() = runTest {
        sync.queueRemove("p1", serverMeal)
        queue("a")

        sync.flush()

        assertEquals(1, remote.added.size)
        assertEquals(1, remote.removed.size)
    }

    @Test
    fun `offline keeps a change queued and counts it as waiting`() = runTest {
        sync.queueRemove("p1", serverMeal)
        remote.changeFailures = mutableListOf(ApiException.NetworkError())

        val result = sync.flush()

        assertEquals(FlushResult(added = 0, failed = 0, waiting = 1), result)
        assertEquals(1, fixture.changes.waiting().single().attempts)
    }

    @Test
    fun `a change the server refuses is flagged, reported and does not hold back the next`() = runTest {
        sync.queueUpdate("p1", serverMeal, com.nutriplan.shared.data.model.UpdateMealRequest(dayIndex = 99))
        sync.queueRemove("p1", com.nutriplan.shared.testing.meal("m2"))
        remote.changeFailures = mutableListOf(ApiException.HttpError(422, null))

        val result = sync.flush()

        assertEquals(FlushResult(added = 1, failed = 1, waiting = 0), result)
        val failed = sync.changeFailures("p1").single()
        assertEquals(PendingFailure.REJECTED, failed.failure)
        assertEquals("m1", failed.mealId)
        assertEquals(listOf("p1" to "m2"), remote.removed)
    }

    @Test
    fun `an edit of a meal that no longer exists is a not found failure`() = runTest {
        sync.queueUpdate("p1", serverMeal, com.nutriplan.shared.data.model.UpdateMealRequest(servings = 2.0))
        remote.changeFailures = mutableListOf(ApiException.HttpError(404, null))

        sync.flush()

        assertEquals(PendingFailure.NOT_FOUND, sync.changeFailures().single().failure)
    }

    @Test
    fun `removing a meal that is already gone counts as removed`() = runTest {
        sync.queueRemove("p1", serverMeal)
        remote.changeFailures = mutableListOf(ApiException.HttpError(404, null))

        val result = sync.flush()

        assertEquals(FlushResult(added = 1, failed = 0, waiting = 0), result)
        assertTrue(sync.changeFailures().isEmpty())
    }

    @Test
    fun `change failures can be dismissed`() = runTest {
        sync.queueUpdate("p1", serverMeal, com.nutriplan.shared.data.model.UpdateMealRequest(servings = 2.0))
        remote.changeFailures = mutableListOf(ApiException.HttpError(422, null))
        sync.flush()

        sync.dismissChangeFailure(sync.changeFailures().single().id)

        assertTrue(sync.changeFailures().isEmpty())
    }

    @Test
    fun `a sent change makes the saved plan stale`() = runTest {
        fixture.cache.upsertPlan(fullPlan("p1", meals = listOf(serverMeal)))
        sync.queueRemove("p1", serverMeal)

        sync.flush()

        assertNull(fixture.cache.getPlan("p1"))
    }

    @Test
    fun `without a change store edits cannot be queued`() {
        val plain = PendingMealSync(remote, store, fixture.cache)

        assertFalse(plain.canQueueChanges)
        assertNull(plain.queueRemove("p1", serverMeal))
        assertNull(plain.queueUpdate("p1", serverMeal, com.nutriplan.shared.data.model.UpdateMealRequest(servings = 2.0)))
        assertTrue(sync.canQueueChanges)
    }}
