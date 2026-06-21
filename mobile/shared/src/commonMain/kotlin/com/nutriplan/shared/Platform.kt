package com.nutriplan.shared

/** Describes the host platform the shared module is running on. */
interface Platform {
    val name: String
}

/** Returns the platform-specific [Platform] implementation. */
expect fun platform(): Platform
