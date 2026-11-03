package com.nutriplan.shared.data.network

import io.ktor.client.HttpClient

/**
 * Creates the AI gateway-edge HTTP client for the current platform.
 *
 * The AI edge is a dedicated client separate from the identity edge: it carries the bearer token
 * itself (no [io.ktor.client.plugins.auth.Auth] plugin) and owns the session-expiry recovery in
 * [com.nutriplan.shared.data.repository.AiRepository], so a 401 there refreshes exactly once and
 * retries the same call. The engine is platform-specific (OkHttp on Android, Darwin on iOS).
 */
internal expect fun createAiClient(): HttpClient