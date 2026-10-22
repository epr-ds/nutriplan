package com.nutriplan.shared.ai

/**
 * How long an AI request has been running, as the screens tell the user (AIA-606). AI answers take
 * a few seconds, so after a while the screens say it is still working rather than look stuck.
 */
enum class AiLoadingStage {
    /** Just asked. */
    STARTED,

    /** Taking a few seconds, as AI answers do. */
    SLOW,

    /** Taking longer than usual; the request times out on its own if it never answers. */
    VERY_SLOW,
    ;

    companion object {
        /** After this long a request is [SLOW]. */
        const val SLOW_AFTER_MILLIS = 4_000L

        /** After this long a request is [VERY_SLOW]. */
        const val VERY_SLOW_AFTER_MILLIS = 12_000L

        /** The stage of a request that has been running for [elapsedMillis]. */
        fun after(elapsedMillis: Long): AiLoadingStage = when {
            elapsedMillis >= VERY_SLOW_AFTER_MILLIS -> VERY_SLOW
            elapsedMillis >= SLOW_AFTER_MILLIS -> SLOW
            else -> STARTED
        }
    }
}
