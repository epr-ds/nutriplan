package com.nutriplan.shared.data.local

import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.PlanMealRecipe
import com.nutriplan.shared.testing.addRequest
import com.nutriplan.shared.testing.newDatabase
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PendingMealStoreTest {

    private val database = newDatabase()
    private val store = PendingMealStore(database)

    private val recipe = PlanMealRecipe(id = "r1", name = "Soup", imageUrl = "https://x/soup.jpg")
    private val info = NutritionalInfo(calories = 600, protein = 40.0)

    private fun enqueue(plan: String = "p1", recipeId: String = "r1", day: Int? = null) =
        store.enqueue(plan, addRequest(recipeId = recipeId), day, recipe.copy(id = recipeId), info)

    @Test
    fun `an empty queue has nothing waiting`() {
        assertTrue(store.waiting().isEmpty())
        assertTrue(store.failed().isEmpty())
    }

    @Test
    fun `enqueue returns the stored request with a fresh id`() {
        val first = enqueue()
        val second = enqueue()

        assertTrue(first.id != second.id)
        assertEquals("p1", first.planId)
        assertEquals("lunch", first.mealType)
        assertEquals(2.0, first.servings)
        assertEquals(0, first.attempts)
        assertNull(first.remoteMealId)
        assertNull(first.failure)
    }

    @Test
    fun `requests come back oldest first with everything that was stored`() {
        val a = enqueue(recipeId = "a", day = 2)
        val b = enqueue(recipeId = "b")

        val waiting = store.waiting()

        assertEquals(listOf(a.id, b.id), waiting.map { it.id })
        assertEquals(2, waiting[0].dayIndex)
        assertNull(waiting[1].dayIndex)
        assertEquals("Soup", waiting[0].recipe.name)
        assertEquals("https://x/soup.jpg", waiting[0].recipe.imageUrl)
        assertEquals(info, waiting[0].nutritionalInfo)
    }

    @Test
    fun `a waiting meal is shown in the plan under a temporary id`() {
        val pending = enqueue(day = 1)

        val meal = pending.toPlanMeal()

        assertTrue(meal.id.startsWith(PENDING_MEAL_ID_PREFIX))
        assertEquals(pending.tempMealId, meal.id)
        assertTrue(meal.isPending)
        assertEquals("lunch", meal.mealType)
        assertEquals(1, meal.dayIndex)
        assertEquals("Soup", meal.recipe?.name)
        assertEquals(info, meal.nutritionalInfo)
    }

    @Test
    fun `the request that creates the meal carries type, recipe and servings`() {
        assertEquals(addRequest(), enqueue().toRequest())
    }

    @Test
    fun `a plan only shows its own waiting meals`() {
        val mine = enqueue(plan = "p1")
        enqueue(plan = "p2")

        assertEquals(listOf(mine.id), store.shownFor("p1").map { it.id })
    }

    @Test
    fun `a meal the server already created is no longer shown as a stand-in but is still waiting`() {
        val pending = enqueue(day = 1)

        store.markAdded(pending.id, "srv-1")

        assertTrue(store.shownFor("p1").isEmpty())
        val waiting = store.waiting().single()
        assertEquals("srv-1", waiting.remoteMealId)
    }

    @Test
    fun `attempts are counted`() {
        val pending = enqueue()

        store.bumpAttempts(pending.id)
        store.bumpAttempts(pending.id)

        assertEquals(2, store.waiting().single().attempts)
    }

    @Test
    fun `a failed request leaves the queue and the plan but is kept to be shown`() {
        val pending = enqueue()

        store.markFailed(pending.id, PendingFailure.REJECTED)

        assertTrue(store.waiting().isEmpty())
        assertTrue(store.shownFor("p1").isEmpty())
        assertEquals(PendingFailure.REJECTED, store.failed().single().failure)
    }

    @Test
    fun `removing forgets a request`() {
        val pending = enqueue()

        store.remove(pending.id)

        assertTrue(store.waiting().isEmpty())
        assertTrue(store.failed().isEmpty())
    }

    @Test
    fun `clear forgets everything, waiting and failed`() {
        enqueue()
        store.markFailed(enqueue().id, PendingFailure.UNKNOWN)

        store.clear()

        assertTrue(store.waiting().isEmpty())
        assertTrue(store.failed().isEmpty())
    }

    @Test
    fun `the queue survives the app restarting`() {
        enqueue(recipeId = "kept")

        val reopened = PendingMealStore(database)

        assertEquals(listOf("kept"), reopened.waiting().map { it.recipeId })
    }

    @Test
    fun `ids keep growing even after earlier requests are removed`() {
        val first = enqueue()
        store.remove(first.id)

        val second = enqueue()

        assertTrue(second.id > first.id, "a stand-in id must never be reused")
    }

    @Test
    fun `an unreadable stored recipe falls back to the recipe id instead of failing`() {
        database.pendingMealQueries.insertPending(
            plan_id = "p1",
            meal_type = "lunch",
            recipe_id = "r9",
            servings = 1.0,
            day_index = null,
            recipe = "not json",
            nutritional_info = "also not json",
        )

        val pending = store.waiting().single()

        assertEquals("r9", pending.recipe.id)
        assertNull(pending.nutritionalInfo)
    }

    @Test
    fun `a failure name from a newer app reads as unknown`() {
        val pending = enqueue()
        database.pendingMealQueries.markFailed("SOMETHING_NEW", pending.id)

        assertEquals(PendingFailure.UNKNOWN, store.failed().single().failure)
    }

    @Test
    fun `only stand-ins are pending`() {
        assertFalse(com.nutriplan.shared.testing.meal("srv-1").isPending)
    }
}
