package com.nutriplan.shared.data.repository

import kotlin.time.Instant
import kotlinx.datetime.Clock

/**
 * Beta feedback submission model.
 */
data class FeedbackSubmission(
    val id: String? = null,
    val category: String,
    val description: String,
    val stepsToReproduce: String?,
    val appVersion: String,
    val deviceModel: String,
    val osVersion: String,
    val userEmail: String?,
    val submittedAt: Instant? = null,
    val synced: Boolean = false
) {
    companion object {
        fun local(
            category: String,
            description: String,
            stepsToReproduce: String? = null,
            appVersion: String = "0.1.0-beta",
            deviceModel: String = "unknown",
            osVersion: String = "unknown",
            userEmail: String? = null
        ) = FeedbackSubmission(
            category = category,
            description = description,
            stepsToReproduce = stepsToReproduce,
            appVersion = appVersion,
            deviceModel = deviceModel,
            osVersion = osVersion,
            userEmail = userEmail,
            submittedAt = Clock.System.now(),
            synced = false
        )
    }
}

/**
 * Repository interface for beta feedback.
 * Implementations handle local storage and sync to backend.
 */
interface FeedbackRepository {
    /** Get all unsynced feedback submissions (for retry) */
    suspend fun getUnsynced(): List<FeedbackSubmission>

    /** Save a new feedback submission locally */
    suspend fun save(submission: FeedbackSubmission): String

    /** Sync local feedback to backend API */
    suspend fun syncAll(): Result<Unit>

    /** Get all feedback submissions (for export/debug) */
    suspend fun getAll(): List<FeedbackSubmission>
}
