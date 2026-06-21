package com.nutriplan.shared

/**
 * Minimal smoke-test entry point used to verify the shared module is wired into both
 * the Android and iOS apps. Real domain logic replaces this in Phase 0.
 */
class Greeting {
    private val platform: Platform = platform()

    fun greet(): String = "NutriPlan running on ${platform.name}"
}
