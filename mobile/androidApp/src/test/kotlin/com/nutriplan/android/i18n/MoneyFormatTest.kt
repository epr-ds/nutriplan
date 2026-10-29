package com.nutriplan.android.i18n

import org.junit.Assert.assertEquals
import org.junit.Test
import java.util.Locale

/** HRD-402: MXN money must render with the MXN code, locale grouping and two decimals. */
class MoneyFormatTest {

    @Test
    fun `mxn currency is rendered with the MXN code grouping and two decimals`() {
        assertEquals("MXN 1,234.56", formatMnx(1234.56, Locale.US))
    }

    @Test
    fun `a whole mnx amount keeps two decimals`() {
        assertEquals("MXN 45.00", formatMnx(45.0, Locale.US))
    }

    @Test
    fun `the mnx grouping follows the locale`() {
        assertEquals("MXN 1.234,56", formatMnx(1234.56, Locale("es", "ES")))
    }
}
