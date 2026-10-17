package com.nutriplan.shared.data.network

/**
 * Header names whose values must never be written to logs.
 *
 * The Ktor `Logging` plugin is configured with [isSensitiveHeader] so bearer tokens, session
 * cookies, and API keys are replaced with a placeholder instead of leaking into logcat/console or
 * crash reports.
 */
val SENSITIVE_HEADERS: Set<String> = setOf(
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
)

/** True when [headerName] (case-insensitive) must be redacted from HTTP logs. */
fun isSensitiveHeader(headerName: String): Boolean =
    headerName.trim().lowercase() in SENSITIVE_HEADERS
