package com.nutriplan.shared.planning

import com.nutriplan.shared.data.local.ChangeKind
import com.nutriplan.shared.data.local.PendingFailure
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.repository.CachedDietaryRepository
import com.nutriplan.shared.testing.QueueFixture
import com.nutriplan.shared.testing.fullPlan
import com.nutriplan.shared.testing.meal
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * DPL-407 in the two screens it touches: the add-meal form queues instead of failing when the server
 * cannot be reached, and the plan sends the queue when it is opened and reports what was refused.
 */
class QueuedMealViewModelsTest {

    private val fixture = QueueFixture()
    private val repository = CachedDietaryRepository(fixture.remote, fixture.cache, fixture.store, fixture.changes)

    private fun addForm() = AddMealViewModel(repository, fixture.sync)

    private suspend fun AddMealViewModel.fill(day: Int? = null) {
        start("p1", "r1")
        onMealTypeChange("dinner")
        onServingsChange("2")
        onDayChange(day)
    }

    // --- add-meal form ---

    @Test
    fun `offline the meal is queued and the form finishes at once`() = runTest {
        val form = addForm()
        form.fill()
        fixture.remote.addFailures = mutableListOf(ApiException.NetworkError())

        form.save()

        val state = form.state.value
        assertTrue(state.isDone)
        assertTrue(state.queued)
        assertNull(state.error)
        assertFalse(state.isSaving)
        val pending = fixture.store.waiting().single()
        assertEquals("p1", pending.planId)
        assertEquals("r1", pending.recipeId)
        assertEquals("dinner", pending.mealType)
        assertEquals(2.0, pending.servings)
        assertEquals("Recipe r1", pending.recipe.name)
    }

    @Test
    fun `a server error queues the meal too`() = runTest {
        val form = addForm()
        form.fill()
        fixture.remote.addFailures = mutableListOf(ApiException.HttpError(503, null))

        form.save()

        assertTrue(form.state.value.queued)
        assertEquals(1, fixture.store.waiting().size)
    }

    @Test
    fun `the chosen day is queued with the meal`() = runTest {
        val form = addForm()
        form.fill(day = 2)
        fixture.remote.addFailures = mutableListOf(ApiException.NetworkError())

        form.save()

        assertEquals(2, fixture.store.waiting().single().dayIndex)
    }

    @Test
    fun `online the meal is added straight away and nothing is queued`() = runTest {
        val form = addForm()
        form.fill()

        form.save()

        assertTrue(form.state.value.isDone)
        assertFalse(form.state.value.queued)
        assertTrue(fixture.store.waiting().isEmpty())
        assertEquals(1, fixture.remote.added.size)
    }

    @Test
    fun `a refused meal is an error, not a queued meal`() = runTest {
        val form = addForm()
        form.fill()
        fixture.remote.addFailures = mutableListOf(ApiException.HttpError(422, null))

        form.save()

        assertEquals(AddMealError.REJECTED, form.state.value.error)
        assertFalse(form.state.value.isDone)
        assertTrue(fixture.store.waiting().isEmpty())
    }

    @Test
    fun `an ended session is an error, not a queued meal`() = runTest {
        val form = addForm()
        form.fill()
        fixture.remote.addFailures = mutableListOf(ApiException.HttpError(401, null))

        form.save()

        assertEquals(AddMealError.SESSION_EXPIRED, form.state.value.error)
        assertTrue(fixture.store.waiting().isEmpty())
    }

    @Test
    fun `if the meal was created and only its day failed nothing is queued`() = runTest {
        val form = addForm()
        form.fill(day = 1)
        fixture.remote.updateFailure = ApiException.NetworkError()

        form.save()

        assertFalse(form.state.value.queued)
        assertEquals("srv-meal-1", form.state.value.addedMealId)
        assertTrue(fixture.store.waiting().isEmpty(), "the meal is on the server; only the day is retried")
    }

    @Test
    fun `without a queue the form fails as before`() = runTest {
        val form = AddMealViewModel(repository)
        form.fill()
        fixture.remote.addFailures = mutableListOf(ApiException.NetworkError())

        form.save()

        assertEquals(AddMealError.NETWORK, form.state.value.error)
        assertFalse(form.state.value.isDone)
    }

    // --- plan detail ---

    private fun detail() = MealPlanDetailViewModel(repository, fixture.sync)

    @Test
    fun `opening the plan sends the queued meals first, so the plan already has them`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(meal("m1")))
        fixture.sync.queueAdd("p1", com.nutriplan.shared.testing.addRequest(), null, com.nutriplan.shared.testing.queuedRecipe())
        val screen = detail()

        screen.load("p1")

        assertEquals(1, fixture.remote.added.size)
        assertTrue(fixture.store.waiting().isEmpty())
        val ids = screen.state.value.plan!!.meals.map { it.id }
        assertEquals(2, ids.size)
        assertTrue(ids.none { it.startsWith("pending-") })
    }

    @Test
    fun `refreshing sends the queue too`() = runTest {
        fixture.remote.plan = fullPlan("p1")
        val screen = detail()
        screen.load("p1")
        fixture.sync.queueAdd("p1", com.nutriplan.shared.testing.addRequest(), null, com.nutriplan.shared.testing.queuedRecipe())

        screen.refresh()

        assertEquals(1, fixture.remote.added.size)
    }

    @Test
    fun `offline the plan still opens, with the queued meal shown as waiting`() = runTest {
        fixture.cache.upsertPlan(fullPlan("p1", meals = listOf(meal("m1"))))
        val pending = fixture.sync.queueAdd(
            "p1",
            com.nutriplan.shared.testing.addRequest(),
            null,
            com.nutriplan.shared.testing.queuedRecipe(),
        )
        fixture.remote.planFailure = ApiException.NetworkError()
        fixture.remote.addFailures = mutableListOf(ApiException.NetworkError())
        val screen = detail()

        screen.load("p1")

        val state = screen.state.value
        assertEquals(listOf("m1", pending.tempMealId), state.plan!!.meals.map { it.id })
        assertEquals(1, fixture.store.waiting().size, "still queued for the next time")
        assertTrue(state.failedAdds.isEmpty())
    }

    @Test
    fun `a meal the server refused is reported, and can be dismissed`() = runTest {
        fixture.remote.plan = fullPlan("p1")
        fixture.sync.queueAdd("p1", com.nutriplan.shared.testing.addRequest(), null, com.nutriplan.shared.testing.queuedRecipe())
        fixture.remote.addFailures = mutableListOf(ApiException.HttpError(404, null))
        val screen = detail()

        screen.load("p1")

        val failed = screen.state.value.failedAdds.single()
        assertEquals(PendingFailure.NOT_FOUND, failed.failure)
        assertEquals("Recipe r1", failed.recipe.name)
        assertTrue(screen.state.value.plan!!.meals.isEmpty(), "rolled back: not in the plan")

        screen.dismissFailedAdd(failed.id)

        assertTrue(screen.state.value.failedAdds.isEmpty())
        assertTrue(fixture.sync.failures().isEmpty())
    }

    @Test
    fun `only this plan's failures are shown`() = runTest {
        fixture.remote.plan = fullPlan("p1")
        fixture.sync.queueAdd("p2", com.nutriplan.shared.testing.addRequest(), null, com.nutriplan.shared.testing.queuedRecipe())
        fixture.remote.addFailures = mutableListOf(ApiException.HttpError(422, null))
        val screen = detail()

        screen.load("p1")

        assertTrue(screen.state.value.failedAdds.isEmpty())
    }

    @Test
    fun `without a queue the plan loads exactly as before`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(meal("m1")))
        val screen = MealPlanDetailViewModel(repository)

        screen.load("p1")

        assertEquals(listOf("m1"), screen.state.value.plan!!.meals.map { it.id })
        assertTrue(screen.state.value.failedAdds.isEmpty())
    }

    // --- edit-meal form: edits and removals ---

    private suspend fun startedEditor(sync: com.nutriplan.shared.data.repository.PendingMealSync? = fixture.sync): EditMealViewModel {
        fixture.remote.plan = fullPlan("p1", meals = listOf(meal("m1", dayIndex = 1)))
        return EditMealViewModel(repository, sync).also { it.start("p1", "m1") }
    }

    @Test
    fun `offline an edit is queued and the form finishes at once`() = runTest {
        val editor = startedEditor()
        editor.onSatisfactionChange(5)
        editor.onServingsChange("3")
        fixture.remote.changeFailures = mutableListOf(ApiException.NetworkError())

        editor.save()

        val state = editor.state.value
        assertTrue(state.isDone)
        assertTrue(state.queued)
        assertNull(state.error)
        val change = fixture.changes.waiting().single()
        assertEquals("m1", change.mealId)
        assertEquals(3.0, change.servings)
        assertEquals(5, change.satisfactionLevel)
        assertNull(change.dayIndex, "only what changed is queued")
    }

    @Test
    fun `a server error queues the edit too`() = runTest {
        val editor = startedEditor()
        editor.onSatisfactionChange(2)
        fixture.remote.changeFailures = mutableListOf(ApiException.HttpError(503, null))

        editor.save()

        assertTrue(editor.state.value.queued)
    }

    @Test
    fun `a refused edit is an error, not a queued change`() = runTest {
        val editor = startedEditor()
        editor.onSatisfactionChange(2)
        fixture.remote.changeFailures = mutableListOf(ApiException.HttpError(422, null))

        editor.save()

        assertEquals(EditMealError.REJECTED, editor.state.value.error)
        assertFalse(editor.state.value.isDone)
        assertTrue(fixture.changes.waiting().isEmpty())
    }

    @Test
    fun `an ended session is an error, not a queued change`() = runTest {
        val editor = startedEditor()
        editor.onSatisfactionChange(2)
        fixture.remote.changeFailures = mutableListOf(ApiException.HttpError(401, null))

        editor.save()

        assertEquals(EditMealError.SESSION_EXPIRED, editor.state.value.error)
        assertTrue(fixture.changes.waiting().isEmpty())
    }

    @Test
    fun `offline a removal is queued and the form finishes at once`() = runTest {
        val editor = startedEditor()
        fixture.remote.changeFailures = mutableListOf(ApiException.NetworkError())

        editor.remove()

        assertTrue(editor.state.value.isDone)
        assertTrue(editor.state.value.queued)
        assertEquals(ChangeKind.REMOVE, fixture.changes.waiting().single().kind)
    }

    @Test
    fun `removing a meal that is already gone is still just done`() = runTest {
        val editor = startedEditor()
        fixture.remote.changeFailures = mutableListOf(ApiException.HttpError(404, null))

        editor.remove()

        assertTrue(editor.state.value.isDone)
        assertFalse(editor.state.value.queued)
        assertTrue(fixture.changes.waiting().isEmpty())
    }

    @Test
    fun `without a queue the edit form fails as before`() = runTest {
        val editor = startedEditor(sync = null)
        editor.onSatisfactionChange(2)
        fixture.remote.changeFailures = mutableListOf(ApiException.NetworkError())

        editor.save()

        assertEquals(EditMealError.NETWORK, editor.state.value.error)
        assertTrue(fixture.changes.waiting().isEmpty())
    }

    @Test
    fun `reopening a meal with a waiting edit shows the edit`() = runTest {
        val first = startedEditor()
        first.onServingsChange("4")
        fixture.remote.changeFailures = mutableListOf(ApiException.NetworkError())
        first.save()

        val second = EditMealViewModel(repository, fixture.sync)
        second.start("p1", "m1")

        assertEquals("4", second.state.value.servings)
    }

    @Test
    fun `editing a meal again while its change waits merges into it`() = runTest {
        val first = startedEditor()
        first.onServingsChange("4")
        fixture.remote.changeFailures = mutableListOf(ApiException.NetworkError())
        first.save()
        val second = EditMealViewModel(repository, fixture.sync)
        second.start("p1", "m1")
        second.onSatisfactionChange(5)
        fixture.remote.changeFailures = mutableListOf(ApiException.NetworkError())

        second.save()

        val change = fixture.changes.waiting().single()
        assertEquals(4.0, change.servings)
        assertEquals(5, change.satisfactionLevel)
    }

    // --- plan detail: refused edits and removals ---

    @Test
    fun `an edit the server refused is reported on the plan, and can be dismissed`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(meal("m1", dayIndex = 1)))
        fixture.sync.queueUpdate("p1", meal("m1"), com.nutriplan.shared.data.model.UpdateMealRequest(dayIndex = 99))
        fixture.remote.changeFailures = mutableListOf(ApiException.HttpError(422, null))
        val screen = detail()

        screen.load("p1")

        val failed = screen.state.value.failedChanges.single()
        assertEquals(PendingFailure.REJECTED, failed.failure)
        assertEquals("m1", failed.mealId)
        assertEquals(1, screen.state.value.plan!!.meals.single().dayIndex, "back to the server's version")

        screen.dismissFailedChange(failed.id)

        assertTrue(screen.state.value.failedChanges.isEmpty())
        assertTrue(fixture.sync.changeFailures().isEmpty())
    }

    @Test
    fun `opening the plan sends queued changes before reading it`() = runTest {
        fixture.remote.plan = fullPlan("p1", meals = listOf(meal("m1", dayIndex = 1)))
        fixture.sync.queueRemove("p1", meal("m1"))
        val screen = detail()

        screen.load("p1")

        assertEquals(listOf("p1" to "m1"), fixture.remote.removed)
        assertTrue(fixture.changes.waiting().isEmpty())
    }

    @Test
    fun `offline the plan opens with the queued removal already applied`() = runTest {
        fixture.cache.upsertPlan(fullPlan("p1", meals = listOf(meal("m1"), meal("m2"))))
        fixture.sync.queueRemove("p1", meal("m1"))
        fixture.remote.planFailure = ApiException.NetworkError()
        fixture.remote.changeFailures = mutableListOf(ApiException.NetworkError())
        val screen = detail()

        screen.load("p1")

        assertEquals(listOf("m2"), screen.state.value.plan!!.meals.map { it.id })
        assertEquals(1, fixture.changes.waiting().size)
    }}
