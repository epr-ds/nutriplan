package com.nutriplan.android.sync

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.work.Configuration
import androidx.work.ListenableWorker
import androidx.work.NetworkType
import androidx.work.WorkInfo
import androidx.work.WorkManager
import androidx.work.testing.TestListenableWorkerBuilder
import androidx.work.testing.WorkManagerTestInitHelper
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.shared.data.repository.FlushResult
import com.nutriplan.shared.data.repository.MealQueueFlusher
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.core.context.startKoin
import org.koin.core.context.stopKoin
import org.koin.dsl.module
import org.robolectric.annotation.Config

/**
 * DPL-407: the offline queue is sent in the background once the device has a network, and a job that
 * cannot finish asks to be retried later instead of losing the meals. Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class MealQueueSyncTest {

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private class FakeFlusher(var outcome: () -> FlushResult) : MealQueueFlusher {
        var calls = 0

        override suspend fun flush(): FlushResult {
            calls++
            return outcome()
        }
    }

    @Before
    fun setUp() {
        WorkManagerTestInitHelper.initializeTestWorkManager(context, Configuration.Builder().build())
    }

    @After
    fun tearDown() {
        runCatching { stopKoin() }
    }

    private fun runWorker(attempt: Int = 0): ListenableWorker.Result = runBlocking {
        TestListenableWorkerBuilder<FlushPendingMealsWorker>(context)
            .setRunAttemptCount(attempt)
            .build()
            .doWork()
    }

    private fun withFlusher(flusher: MealQueueFlusher) {
        startKoin { modules(module { single<MealQueueFlusher> { flusher } }) }
    }

    // --- the job ---

    @Test
    fun `an emptied queue finishes the job`() {
        val flusher = FakeFlusher { FlushResult(added = 2, failed = 0, waiting = 0) }
        withFlusher(flusher)

        assertEquals(ListenableWorker.Result.success(), runWorker())
        assertEquals(1, flusher.calls)
    }

    @Test
    fun `an empty queue is a successful no-op`() {
        withFlusher(FakeFlusher { FlushResult(0, 0, 0) })

        assertEquals(ListenableWorker.Result.success(), runWorker())
    }

    @Test
    fun `meals the server refused do not keep the job running`() {
        withFlusher(FakeFlusher { FlushResult(added = 0, failed = 1, waiting = 0) })

        assertEquals(ListenableWorker.Result.success(), runWorker())
    }

    @Test
    fun `meals that are still waiting ask for a retry later`() {
        withFlusher(FakeFlusher { FlushResult(added = 0, failed = 0, waiting = 2) })

        assertEquals(ListenableWorker.Result.retry(), runWorker())
    }

    @Test
    fun `a flush that throws asks for a retry later`() {
        withFlusher(FakeFlusher { error("boom") })

        assertEquals(ListenableWorker.Result.retry(), runWorker())
    }

    @Test
    fun `after too many tries the job gives up, and the next app start asks again`() {
        withFlusher(FakeFlusher { FlushResult(added = 0, failed = 0, waiting = 1) })

        assertEquals(ListenableWorker.Result.failure(), runWorker(attempt = MAX_RUN_ATTEMPTS))
        assertEquals(ListenableWorker.Result.retry(), runWorker(attempt = MAX_RUN_ATTEMPTS - 1))
    }

    @Test
    fun `without the app's dependencies the job fails instead of crashing`() {
        assertEquals(ListenableWorker.Result.failure(), runWorker())
    }

    // --- scheduling ---

    private fun jobs(): List<WorkInfo> =
        WorkManager.getInstance(context).getWorkInfosForUniqueWork(MEAL_QUEUE_WORK_NAME).get()

    @Test
    fun `asking for a sync queues one background job that needs a network`() {
        WorkManagerSyncScheduler(context).requestSync()

        val job = jobs().single()
        assertEquals(WorkInfo.State.ENQUEUED, job.state)
        assertEquals(NetworkType.CONNECTED, job.constraints.requiredNetworkType)
    }

    @Test
    fun `asking again while a job is waiting does not queue another`() {
        val scheduler = WorkManagerSyncScheduler(context)

        scheduler.requestSync()
        scheduler.requestSync()
        scheduler.requestSync()

        assertEquals(1, jobs().size)
    }

    @Test
    fun `the job has a name that is stable across app starts`() {
        assertTrue(MEAL_QUEUE_WORK_NAME.isNotBlank())
        WorkManagerSyncScheduler(context).requestSync()

        assertEquals(1, WorkManager.getInstance(context).getWorkInfosForUniqueWork("meal-queue-sync").get().size)
    }
}
