package com.nutriplan.android.a11y

import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher

/**
 * IDN-705: reusable semantics matchers for the accessibility checks.
 *
 * These assert the accessible properties screen readers rely on (a live region so an error is
 * announced, or a field-level error association). They run on the JVM via Robolectric, so they are
 * a deterministic regression guard without an emulator.
 */

/** Matches a node announced when it changes (used for error messages). */
fun hasLiveRegion(mode: LiveRegionMode = LiveRegionMode.Polite): SemanticsMatcher =
    SemanticsMatcher.expectValue(SemanticsProperties.LiveRegion, mode)

/** Matches a node carrying the given field-level [error] message. */
fun hasError(error: String): SemanticsMatcher =
    SemanticsMatcher.expectValue(SemanticsProperties.Error, error)
