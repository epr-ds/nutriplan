package com.nutriplan.android.ai

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.a11y.hasLiveRegion
import com.nutriplan.android.screen.ai.AiErrorCard
import com.nutriplan.android.screen.ai.AiLoadingSkeleton
import com.nutriplan.android.screen.ai.AiStateTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.ai.AiLoadingStage
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * AIA-606: the AI loading skeleton says what is happening (and that it is still working as time
 * goes on), and the AI error card offers a retry and, where there is one, a non-AI way out.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h1200dp", application = TestApplication::class)
class AiStatesTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int): String = context.getString(id)

    private fun renderSkeleton(stage: AiLoadingStage) {
        compose.setContent {
            NutriPlanTheme { AiLoadingSkeleton(stage = stage, description = "Getting recommendations", cards = 3) }
        }
    }

    @Test
    fun `the skeleton is one labelled indeterminate progress indicator with placeholder cards`() {
        renderSkeleton(AiLoadingStage.STARTED)

        val indeterminate = SemanticsMatcher.expectValue(
            SemanticsProperties.ProgressBarRangeInfo,
            ProgressBarRangeInfo.Indeterminate,
        )
        compose.onNodeWithContentDescription("Getting recommendations").assert(indeterminate)
        compose.onAllNodesWithTag(AiStateTestTags.SKELETON).assertCountEquals(3)
    }

    @Test
    fun `the status says the request was just made`() {
        renderSkeleton(AiLoadingStage.STARTED)

        compose.onNodeWithTag(AiStateTestTags.STATUS)
            .assert(hasText(str(R.string.ai_loading_started)))
            .assert(hasLiveRegion())
    }

    @Test
    fun `after a few seconds the status says it is still working`() {
        renderSkeleton(AiLoadingStage.SLOW)

        compose.onNodeWithTag(AiStateTestTags.STATUS).assert(hasText(str(R.string.ai_loading_slow)))
    }

    @Test
    fun `after longer the status says it is taking longer than usual`() {
        renderSkeleton(AiLoadingStage.VERY_SLOW)

        compose.onNodeWithTag(AiStateTestTags.STATUS).assert(hasText(str(R.string.ai_loading_very_slow)))
    }

    private class Calls {
        var retries = 0
        var fallbacks = 0
    }

    private fun renderError(withFallback: Boolean, retryEnabled: Boolean = true): Calls {
        val calls = Calls()
        compose.setContent {
            NutriPlanTheme {
                AiErrorCard(
                    message = "Took too long.",
                    onRetry = { calls.retries++ },
                    messageTestTag = "message",
                    retryEnabled = retryEnabled,
                    fallbackLabel = "Browse recipes".takeIf { withFallback },
                    onFallback = { calls.fallbacks++ },
                )
            }
        }
        return calls
    }

    @Test
    fun `the error is announced and can be retried`() {
        val calls = renderError(withFallback = false)

        compose.onNodeWithTag("message").assert(hasText("Took too long.")).assert(hasLiveRegion())
        compose.onNodeWithTag(AiStateTestTags.RETRY).assert(hasText(str(R.string.ai_retry))).performClick()

        assertEquals(1, calls.retries)
        compose.onNodeWithTag(AiStateTestTags.FALLBACK).assertDoesNotExist()
    }

    @Test
    fun `the ai error retry button is announced to screen readers`() {
        val calls = renderError(withFallback = false)

        compose.onNode(
            hasTestTag(AiStateTestTags.RETRY) and hasContentDescription(str(R.string.ai_retry)),
        ).assertIsDisplayed()
        compose.onNodeWithTag(AiStateTestTags.RETRY).assert(hasText(str(R.string.ai_retry)))
        assertEquals(1, calls.retries)
    }

    @Test
    fun `a fallback is offered when there is one`() {
        val calls = renderError(withFallback = true)

        compose.onNodeWithTag(AiStateTestTags.FALLBACK).assert(hasText("Browse recipes")).performClick()

        assertEquals(1, calls.fallbacks)
    }

    @Test
    fun `no retry while a new request is already running`() {
        renderError(withFallback = false, retryEnabled = false)

        compose.onNodeWithTag(AiStateTestTags.RETRY).assertIsNotEnabled()
    }
}
