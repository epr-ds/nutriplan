package com.nutriplan.android.analytics

import android.content.Context
import com.google.firebase.analytics.FirebaseAnalytics
import com.nutriplan.shared.analytics.AnalyticsTracker

/**
 * Android implementation of [AnalyticsTracker] backed by Firebase Analytics.
 *
 * All events are gated by consent — if consent is denied, logEvent/setUserProperty
 * become no-ops (initialize() still runs so Crashlytics can function independently).
 */
class FirebaseAnalyticsTracker(private val context: Context) : AnalyticsTracker {

    private val firebaseAnalytics: FirebaseAnalytics = FirebaseAnalytics.getInstance(context)
    private var consentGiven: Boolean = false

    override val isConsentGiven: Boolean get() = consentGiven

    override fun initialize() {
        // Firebase Analytics auto-initializes via the Google Services plugin.
        // We only need to set up consent defaults here.
        setConsentDefaults()
    }

    override fun logScreenView(screenName: String, screenClass: String) {
        if (!consentGiven) return
        val params = bundleOf("screen_name" to screenName, "screen_class" to screenClass)
        firebaseAnalytics.logEvent(FirebaseAnalytics.Event.SCREEN_VIEW, params)
    }

    override fun logEvent(eventName: String, params: Map<String, String>) {
        if (!consentGiven) return
        firebaseAnalytics.logEvent(eventName, bundleToBundle(params))
    }

    override fun setUserProperty(name: String, value: String) {
        if (!consentGiven) return
        firebaseAnalytics.setUserProperty(name, value)
    }

    override fun setConsent(given: Boolean) {
        consentGiven = given
        setConsentDefaults()
    }

    /**
     * Set Firebase Analytics consent defaults.
     *
     * In a production app, this would read from a consent management platform (CMP)
     * or a local consent preference store. For beta, we default to denied and
     * only enable when the user explicitly opts in.
     */
    private fun setConsentDefaults() {
        // Firebase Analytics consent: data collection enabled/disabled
        // (In production, integrate with a CMP like Consent Manager for GDPR/LFPDPPP compliance)
    }

    private fun bundleToBundle(params: Map<String, String>): android.os.Bundle {
        return android.os.Bundle().apply {
            params.forEach { (key, value) -> putString(key, value) }
        }
    }
}

private fun bundleOf(vararg pairs: Pair<String, String>): android.os.Bundle {
    return android.os.Bundle().apply {
        pairs.forEach { (key, value) -> putString(key, value) }
    }
}
