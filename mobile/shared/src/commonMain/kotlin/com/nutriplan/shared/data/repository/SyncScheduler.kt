package com.nutriplan.shared.data.repository

/**
 * Asks the platform to send the offline queue (DPL-407) as soon as the server can be reached,
 * even if the app is closed in the meantime.
 *
 * The shared code only says *that* a sync is wanted; each platform decides how to wait for the
 * network (Android uses WorkManager). Calling it again while a sync is already requested is fine.
 */
fun interface SyncScheduler {
    fun requestSync()

    companion object {
        /** For platforms (and tests) with nothing to schedule: the queue is then sent when a plan is opened. */
        val None = SyncScheduler {}
    }
}

/** Something that sends the offline queue; what the platform's background job calls. */
fun interface MealQueueFlusher {
    suspend fun flush(): FlushResult
}
