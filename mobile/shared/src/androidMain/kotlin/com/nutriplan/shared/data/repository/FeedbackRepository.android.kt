package com.nutriplan.shared.data.repository

import android.content.Context
import android.content.SharedPreferences
import kotlin.time.Instant
import org.json.JSONArray
import org.json.JSONObject

/**
 * Android-specific FeedbackRepository implementation using SharedPreferences for local storage.
 */
class FeedbackRepositoryAndroid(
    private val context: Context,
    private val apiClient: FeedbackApiClient? = null
) : FeedbackRepository {

    companion object {
        private const val PREFS_NAME = "nutriplan_feedback"
        private const val KEY_SUBMISSIONS = "feedback_submissions"
    }

    private val prefs: SharedPreferences by lazy {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    }

    override suspend fun getUnsynced(): List<FeedbackSubmission> {
        return getAll().filterNot { it.synced }
    }

    override suspend fun save(submission: FeedbackSubmission): String {
        val id = submission.id ?: java.util.UUID.randomUUID().toString()
        val submissions = getSubmissionsList()
        
        // Update or add the submission
        var found = false
        for (i in 0 until submissions.length()) {
            if (submissions.getJSONObject(i).optString("id") == id) {
                submissions.put(i, toJSONObject(id, submission))
                found = true
                break
            }
        }
        
        // Add new if not found
        if (!found) {
            submissions.put(toJSONObject(id, submission))
        }
        
        prefs.edit().putString(KEY_SUBMISSIONS, submissions.toString()).apply()
        return id
    }

    override suspend fun syncAll(): Result<Unit> {
        val unsynced = getUnsynced()
        if (unsynced.isEmpty()) return Result.success(Unit)
        
        apiClient?.submitFeedback(unsynced)?.onSuccess {
            // Mark as synced
            for (submission in unsynced) {
                val updated = submission.copy(synced = true, submittedAt = Instant.now())
                save(updated)
            }
        }
        
        return Result.success(Unit)
    }

    override suspend fun getAll(): List<FeedbackSubmission> {
        val jsonStr = prefs.getString(KEY_SUBMISSIONS, "[]") ?: "[]"
        val array = JSONArray(jsonStr)
        val submissions = mutableListOf<FeedbackSubmission>()
        
        for (i in 0 until array.length()) {
            val obj = array.getJSONObject(i)
            submissions.add(
                FeedbackSubmission(
                    id = obj.optString("id"),
                    category = obj.optString("category"),
                    description = obj.optString("description"),
                    stepsToReproduce = obj.optString("stepsToReproduce", null),
                    appVersion = obj.optString("appVersion"),
                    deviceModel = obj.optString("deviceModel"),
                    osVersion = obj.optString("osVersion"),
                    userEmail = obj.optString("userEmail", null).takeIf { it.isNotEmpty() },
                    synced = obj.optBoolean("synced")
                )
            )
        }
        
        return submissions
    }

    private fun toJSONObject(id: String, submission: FeedbackSubmission): JSONObject {
        return JSONObject().apply {
            put("id", id)
            put("category", submission.category)
            put("description", submission.description)
            put("stepsToReproduce", submission.stepsToReproduce ?: "")
            put("appVersion", submission.appVersion)
            put("deviceModel", submission.deviceModel)
            put("osVersion", submission.osVersion)
            put("userEmail", submission.userEmail ?: "")
            put("synced", submission.synced)
        }
    }

    private fun getSubmissionsList(): JSONArray {
        val jsonStr = prefs.getString(KEY_SUBMISSIONS, "[]") ?: "[]"
        return try {
            JSONArray(jsonStr)
        } catch (e: Exception) {
            JSONArray()
        }
    }
}

/**
 * Simple HTTP client for feedback API.
 */
interface FeedbackApiClient {
    suspend fun submitFeedback(submissions: List<FeedbackSubmission>): Result<Unit>
}
