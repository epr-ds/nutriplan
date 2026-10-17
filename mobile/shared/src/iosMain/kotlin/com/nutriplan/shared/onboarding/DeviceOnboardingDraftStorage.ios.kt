package com.nutriplan.shared.onboarding

import platform.Foundation.NSUserDefaults

/**
 * iOS [OnboardingDraftStorage]: the draft lives in `NSUserDefaults`. It is non-sensitive, so it is
 * not stored in the Keychain (unlike the tokens).
 */
actual class DeviceOnboardingDraftStorage : OnboardingDraftStorage {

    private val defaults = NSUserDefaults.standardUserDefaults

    actual override fun loadDraft(): String? = defaults.stringForKey(KEY_DRAFT)

    actual override fun saveDraft(draft: String) {
        defaults.setObject(draft, KEY_DRAFT)
    }

    actual override fun clearDraft() {
        defaults.removeObjectForKey(KEY_DRAFT)
    }

    private companion object {
        const val KEY_DRAFT = "onboarding.draft"
    }
}
