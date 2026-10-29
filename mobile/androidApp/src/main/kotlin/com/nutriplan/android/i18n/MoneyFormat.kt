package com.nutriplan.android.i18n

import java.util.Locale

/** MXN money: the MXN code, locale grouping and two decimals (e.g. "MXN 1,234.56"). */
internal fun formatMnx(amount: Double?, locale: Locale = Locale.getDefault()): String {
    val value = amount ?: 0.0
    val text = String.format(locale, "%,.2f", value)
    return "MXN " + text
}