package com.nutriplan.shared.onboarding

import android.content.Context
import android.content.SharedPreferences

/**
 * Android [OnboardingDraftStorage]: the draft lives in a private `SharedPreferences` file. It is
 * non-sensitive, so it is not encrypted with the Keystore (unlike the tokens).
 */
actual class DeviceOnboardingDraftStorage(context: Context) : OnboardingDraftStorage {

    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    actual override fun loadDraft(): String? = prefs.getString(KEY_DRAFT, null)

    actual override fun saveDraft(draft: String) {
        prefs.edit().putString(KEY_DRAFT, draft).apply()
    }

    actual override fun clearDraft() {
        prefs.edit().remove(KEY_DRAFT).apply()
    }

    private companion object {
        const val PREFS_NAME = "nutriplan_onboarding"
        const val KEY_DRAFT = "draft"
    }
}
