package com.nutriplan.shared.data

/**
 * Deployment environments the app can point at.
 *
 * [baseUrl] is the API gateway origin for the environment; [ApiConfig] appends the service paths.
 * The active environment is chosen at startup (Android: `BuildConfig.API_ENVIRONMENT`, default
 * `dev`; release builds pin `prod`) and can be overridden for local development.
 */
enum class ApiEnvironment(val baseUrl: String) {
    /** Android emulator loopback to a locally running gateway/compose stack. */
    LOCAL("http://10.0.2.2:8080"),
    DEV("https://dev-api.nutriplan.app"),
    STAGE("https://stage-api.nutriplan.app"),
    PROD("https://api.nutriplan.app"),
    ;

    companion object {
        /**
         * Resolve an environment from a case-insensitive name, falling back to [PROD] for
         * unknown or missing values so a misconfigured build never silently points at dev.
         */
        fun fromName(value: String?): ApiEnvironment =
            entries.firstOrNull { it.name.equals(value?.trim(), ignoreCase = true) } ?: PROD
    }
}
