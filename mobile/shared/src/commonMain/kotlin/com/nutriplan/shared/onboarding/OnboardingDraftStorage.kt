package com.nutriplan.shared.onboarding

/**
 * Somewhere to keep the in-progress onboarding draft between wizard instances.
 *
 * The draft is stored as an opaque string (JSON) so the platform implementation stays a dumb
 * key-value store. When the user finishes, the draft is cleared.
 */
interface OnboardingDraftStorage {
    /** The stored draft, or null if there is none. */
    fun loadDraft(): String?

    /** Replace the stored draft. */
    fun saveDraft(draft: String)

    /** Remove the stored draft (onboarding finished). */
    fun clearDraft()
}

/**
 * [OnboardingDraftStorage] backed by the platform's private key-value store.
 *
 * - Android: private `SharedPreferences`.
 * - iOS: `NSUserDefaults`.
 *
 * The password-free draft is non-sensitive, so it does not need the secure stores used for tokens.
 */
expect class DeviceOnboardingDraftStorage : OnboardingDraftStorage {
    override fun loadDraft(): String?
    override fun saveDraft(draft: String)
    override fun clearDraft()
}
