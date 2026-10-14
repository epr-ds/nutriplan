package com.nutriplan.shared.analytics

/**
 * Platform-agnostic analytics tracker interface.
 *
 * Android implementation uses Firebase Analytics; iOS would use FirebaseAnalytics or Mixpanel.
 * All events are consent-gated — callers must check [isConsentGiven] before tracking.
 */
interface AnalyticsTracker {

    /** Whether the user has given consent for analytics. */
    val isConsentGiven: Boolean

    /** Initialize the tracker (called once at app startup). */
    fun initialize()

    /** Log a screen view event. */
    fun logScreenView(screenName: String, screenClass: String)

    /** Log a custom event with optional parameters. */
    fun logEvent(eventName: String, params: Map<String, String> = emptyMap())

    /** Set a user property (e.g. activation status, retention cohort). */
    fun setUserProperty(name: String, value: String)

    /** Set the consent state (called when user grants/denies consent). */
    fun setConsent(given: Boolean)
}
