package com.nutriplan.android.sync

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.nutriplan.shared.data.repository.MealQueueFlusher
import com.nutriplan.shared.data.repository.SyncScheduler
import org.koin.core.context.GlobalContext
import java.util.concurrent.TimeUnit

/** The name of the unique background job that sends the offline queue (DPL-407). */
const val MEAL_QUEUE_WORK_NAME = "meal-queue-sync"

/** How many times one job retries before it gives up; the next app start asks for a new one. */
internal const val MAX_RUN_ATTEMPTS = 8

private const val BACKOFF_SECONDS = 30L

/**
 * Sends the meals added while offline as soon as the device has a network connection, even if the
 * app was closed in between (DPL-407). Only one such job is ever queued: asking again while one is
 * pending changes nothing.
 */
class WorkManagerSyncScheduler(private val context: Context) : SyncScheduler {

    override fun requestSync() {
        val request = OneTimeWorkRequestBuilder<FlushPendingMealsWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, BACKOFF_SECONDS, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(MEAL_QUEUE_WORK_NAME, ExistingWorkPolicy.KEEP, request)
    }
}

/**
 * The background job: flush the queue. Meals that could not be sent yet (the server is down, or the
 * session ended) make it ask to be retried later with a growing delay; a queue that is empty, or
 * left only with meals the server refused, is done.
 */
class FlushPendingMealsWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val flusher = GlobalContext.getOrNull()?.getOrNull<MealQueueFlusher>() ?: return Result.failure()
        val outcome = try {
            flusher.flush()
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            if (e is kotlin.coroutines.cancellation.CancellationException) throw e
            return retryOrGiveUp()
        }
        return if (outcome.waiting > 0) retryOrGiveUp() else Result.success()
    }

    private fun retryOrGiveUp(): Result =
        if (runAttemptCount >= MAX_RUN_ATTEMPTS) Result.failure() else Result.retry()
}
