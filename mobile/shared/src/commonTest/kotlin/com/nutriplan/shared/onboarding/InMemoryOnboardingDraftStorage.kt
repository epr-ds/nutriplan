package com.nutriplan.shared.onboarding

/** In-memory [OnboardingDraftStorage] for tests. */
internal class InMemoryOnboardingDraftStorage(initial: String? = null) : OnboardingDraftStorage {

    var draft: String? = initial
        private set

    override fun loadDraft(): String? = draft

    override fun saveDraft(draft: String) {
        this.draft = draft
    }

    override fun clearDraft() {
        draft = null
    }
}
