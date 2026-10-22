package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.testing.QueueFixture
import com.nutriplan.shared.testing.addRequest
import com.nutriplan.shared.testing.fullPlan
import com.nutriplan.shared.testing.meal
import com.nutriplan.shared.testing.queuedRecipe
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * DPL-407: a plan read shows the meals that are still queued on top of what the server (or the saved
 * copy) says. The server wins on refresh; the queued writes are the later ones.
 */
class CachedDietaryRepositoryQueueTest {

    private val fixture = QueueFixture()
    private val repository = CachedDietaryRepository(fixture.remote, fixture.cache, fixture.store, fixture.changes)

    private fun queue(recipeId: String = "r1", plan: String = "p1", day: Int? = 1) =
        fixture.sync.queueAdd(plan, addRequest(recipeId = recipeId), day, queuedRecipe(recipeId))

    @Test
    fun `a plan read online includes the queued meals after the server's meals`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(meal("m1")))
        val pending = queue()

        val plan = repository.getMealPlan("p1")

        assertEquals(listOf("m1", pending.tempMealId), plan.meals.map { it.id })
        val standIn = plan.meals.last()
        assertEquals(1, standIn.dayIndex)
        assertEquals("Recipe r1", standIn.recipe?.name)
    }

    @Test
    fun `the saved copy holds the server's plan, not the stand-ins`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(meal("m1")))
        queue()

        repository.getMealPlan("p1")

        assertEquals(listOf("m1"), fixture.cache.getPlan("p1")!!.meals.map { it.id })
    }

    @Test
    fun `offline the saved plan is shown with the queued meals on top`() = runTest {
        fixture.cache.upsertPlan(fullPlan("p1", meals = listOf(meal("m1"))))
        fixture.remote.planFailure = ApiException.NetworkError()
        val pending = queue()

        val plan = repository.getMealPlan("p1")

        assertEquals(listOf("m1", pending.tempMealId), plan.meals.map { it.id })
    }

    @Test
    fun `without queued meals the plan is exactly what the server sent`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(meal("m1")))

        assertEquals(listOf("m1"), repository.getMealPlan("p1").meals.map { it.id })
    }

    @Test
    fun `another plan's queued meals are not shown`() = runTest {
        fixture.remote.plan = fullPlan("p1")
        queue(plan = "p2")

        assertTrue(repository.getMealPlan("p1").meals.isEmpty())
    }

    @Test
    fun `after the queue is sent the real meal replaces the stand-in`() = runTest {
        fixture.remote.plan = fullPlan("p1")
        queue()
        assertEquals(1, repository.getMealPlan("p1").meals.size)

        fixture.sync.flush()
        val plan = repository.getMealPlan("p1")

        assertEquals(1, plan.meals.size)
        assertTrue(plan.meals.none { it.id.startsWith("pending-") }, "the server's own meal, not a stand-in")
    }

    @Test
    fun `a refused meal disappears from the plan`() = runTest {
        fixture.remote.plan = fullPlan("p1")
        queue()
        fixture.remote.addFailures = mutableListOf(ApiException.HttpError(422, null))

        fixture.sync.flush()

        assertTrue(repository.getMealPlan("p1").meals.isEmpty())
    }

    @Test
    fun `without a queue store the repository behaves as before`() = runTest {
        val plain = CachedDietaryRepository(fixture.remote, fixture.cache)
        fixture.remote.plan = fullPlan("p1", meals = listOf(meal("m1")))
        queue()

        assertEquals(listOf("m1"), plain.getMealPlan("p1").meals.map { it.id })
    }

    // --- queued edits and removals ---

    private val server = meal("m1", dayIndex = 0, calories = 500)

    @Test
    fun `a queued edit is shown on the meal and marked as waiting`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(server))
        fixture.sync.queueUpdate(
            "p1",
            server,
            com.nutriplan.shared.data.model.UpdateMealRequest(dayIndex = 3, satisfactionLevel = 2),
        )

        val shown = repository.getMealPlan("p1").meals.single()

        assertEquals(3, shown.dayIndex)
        assertEquals(2, shown.satisfactionLevel)
        assertEquals(1.5, shown.servings, "untouched fields stay as the server has them")
        assertTrue(shown.syncPending)
    }

    @Test
    fun `new servings scale the nutrition shown`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(server))
        fixture.sync.queueUpdate("p1", server, com.nutriplan.shared.data.model.UpdateMealRequest(servings = 3.0))

        val shown = repository.getMealPlan("p1").meals.single()

        // 1.5 servings -> 3 servings doubles it.
        assertEquals(1000, shown.nutritionalInfo?.calories)
        assertEquals(51.0, shown.nutritionalInfo?.protein)
    }

    @Test
    fun `a queued removal hides the meal`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(server, meal("m2")))
        fixture.sync.queueRemove("p1", server)

        assertEquals(listOf("m2"), repository.getMealPlan("p1").meals.map { it.id })
    }

    @Test
    fun `an edit and a removal of the same meal leave it removed`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(server))
        fixture.sync.queueUpdate("p1", server, com.nutriplan.shared.data.model.UpdateMealRequest(servings = 2.0))
        fixture.sync.queueRemove("p1", server)

        assertTrue(repository.getMealPlan("p1").meals.isEmpty())
        assertEquals(1, fixture.changes.waiting().size, "only the removal is queued")
    }

    @Test
    fun `later edits of the same meal merge, the last write winning`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(server))
        fixture.sync.queueUpdate("p1", server, com.nutriplan.shared.data.model.UpdateMealRequest(servings = 2.0, dayIndex = 1))
        fixture.sync.queueUpdate("p1", server, com.nutriplan.shared.data.model.UpdateMealRequest(servings = 4.0))

        val shown = repository.getMealPlan("p1").meals.single()

        assertEquals(4.0, shown.servings)
        assertEquals(1, shown.dayIndex)
        assertEquals(1, fixture.changes.waiting().size)
    }

    @Test
    fun `offline the saved plan is shown with the queued changes applied`() = runTest {
        fixture.cache.upsertPlan(fullPlan("p1", meals = listOf(server, meal("m2"))))
        fixture.remote.planFailure = ApiException.NetworkError()
        fixture.sync.queueRemove("p1", server)

        assertEquals(listOf("m2"), repository.getMealPlan("p1").meals.map { it.id })
    }

    @Test
    fun `the saved copy keeps the server's meals, not the queued changes`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(server))
        fixture.sync.queueRemove("p1", server)

        repository.getMealPlan("p1")

        assertEquals(listOf("m1"), fixture.cache.getPlan("p1")!!.meals.map { it.id })
    }

    @Test
    fun `after the change is sent the server's own version is shown`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(server))
        fixture.sync.queueUpdate("p1", server, com.nutriplan.shared.data.model.UpdateMealRequest(dayIndex = 3))
        fixture.sync.flush()

        val shown = repository.getMealPlan("p1").meals.single()

        assertEquals(0, shown.dayIndex, "the fake server did not store the edit; the point is the overlay is gone")
        assertFalse(shown.syncPending)
    }

    @Test
    fun `a refused change disappears from the plan`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(server))
        fixture.sync.queueUpdate("p1", server, com.nutriplan.shared.data.model.UpdateMealRequest(dayIndex = 99))
        fixture.remote.changeFailures = mutableListOf(ApiException.HttpError(422, null))
        fixture.sync.flush()

        assertEquals(0, repository.getMealPlan("p1").meals.single().dayIndex)
    }}
