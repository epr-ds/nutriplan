package com.nutriplan.shared.data

/** Central place for API endpoint configuration consumed by the data layer. */
object ApiConfig {
    const val BASE_URL: String = "https://api.nutriplan.app"

    const val IDENTITY: String = "$BASE_URL/identity/v1"
    const val DIETARY: String = "$BASE_URL/dietary/v1"
    const val COMMERCE: String = "$BASE_URL/commerce/v1"
}
