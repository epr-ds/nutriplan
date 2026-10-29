package com.nutriplan.android.i18n

import org.junit.Assert.assertEquals
import org.junit.Test
import java.util.Locale

/** HRD-403 — store listing copy is localized per language. */
class StoreMetadataFormatTest {

    @Test
    fun `store listing copy keeps the default copy for the english locale`() {
        val listing = StoreListing(
            title = "NutriPlan: Planes saludables",
            subtitle = "Planes de comidas saludables",
            description = "Planes de comidas saludables para cuidar tu nutrición",
            keywords = listOf("nutriplan", "planes", "salud"),
        )
        assertEquals(listing, localizeStoreListing(listing, Locale.US))
    }

    @Test
    fun `store listing copy is localized for the spanish locale`() {
        val listing = StoreListing(
            title = "NutriPlan: Planes saludables",
            subtitle = "Planes de comidas saludables",
            description = "Planes de comidas saludables para cuidar tu nutrición",
            keywords = listOf("nutriplan", "planes", "salud"),
        )
        val localized = localizeStoreListing(listing, Locale("es", "ES"))
        assertEquals("NutriPlan: Planes saludables", localized.title)
        assertEquals("Planes de comidas saludables", localized.subtitle)
    }
}