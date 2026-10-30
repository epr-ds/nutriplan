package com.nutriplan.android.i18n

import java.util.Locale

/** HRD-403: store listing metadata — title, subtitle, description and ASO keywords. */
data class StoreListing(
    val title: String,
    val subtitle: String,
    val description: String,
    val keywords: List<String>,
)

/** HRD-403: Spanish copy of the store listing. */
private val spanishStoreListing = StoreListing(
    title = "NutriPlan: Planes saludables",
    subtitle = "Planes de comidas saludables",
    description = "Planes de comidas saludables para cuidar tu nutrición",
    keywords = listOf("nutriplan", "planes", "salud"),
)

/**
 * HRD-403: store listing copy localized for the shopper's locale. Spanish locales get the Spanish
 * copy; every other locale keeps the listing it was given (the default / English copy).
 */
internal fun localizeStoreListing(listing: StoreListing, locale: Locale): StoreListing =
    if (locale.language == "es") spanishStoreListing else listing