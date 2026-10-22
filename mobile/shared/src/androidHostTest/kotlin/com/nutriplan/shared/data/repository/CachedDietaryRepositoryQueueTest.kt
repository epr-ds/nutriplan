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
import kotlin.test.assertTrue

/**
 * DPL-407: a plan read shows the meals that are still queued on top of what the server (or the saved
 * copy) says. The server wins on refresh; the queued writes are the later ones.
 */
class CachedDietaryRepositoryQueueTest {

    private val fixture = QueueFixture()
    private val repository = CachedDietaryRepository(fixture.remote, fixture.cache, fixture.store)

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
}
