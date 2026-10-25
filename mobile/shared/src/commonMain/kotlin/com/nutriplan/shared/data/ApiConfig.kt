package com.nutriplan.shared.data

/**
 * Central place for API endpoint configuration consumed by the data layer.
 *
 * The active [environment] selects the gateway origin; every service URL is derived from it, so
 * switching environments (local/dev/stage/prod) is a single assignment at startup. Defaults to
 * [ApiEnvironment.PROD]; call [configure] before the HTTP client is created.
 */
object ApiConfig {

    /** Active deployment environment. Defaults to production. */
    var environment: ApiEnvironment = ApiEnvironment.PROD

    /** Point the data layer at [environment]. */
    fun configure(environment: ApiEnvironment) {
        this.environment = environment
    }

    /** Restore the production default (used by tests). */
    fun reset() {
        environment = ApiEnvironment.PROD
    }

    val BASE_URL: String get() = environment.baseUrl

    val IDENTITY: String get() = "$BASE_URL/identity/v1"
    val DIETARY: String get() = "$BASE_URL/dietary/v1"
    val AI: String get() = "$BASE_URL/ai/v1"
    val COMMERCE: String get() = "$BASE_URL/commerce/v1"
    val NOTIFICATION: String get() = "$BASE_URL/notifications/v1"
}
