package com.nutriplan.android.screen.ai

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.shared.ai.AiLoadingStage
import kotlinx.coroutines.delay

/** Test tags for the shared AI loading and error states (AIA-606). */
object AiStateTestTags {
    const val STATUS = "ai_state_status"
    const val SKELETON = "ai_state_skeleton"
    const val RETRY = "ai_state_retry"
    const val FALLBACK = "ai_state_fallback"
}

/**
 * How long the current AI request has been running, re-evaluated while [isLoading]; back to
 * [AiLoadingStage.STARTED] for the next request.
 */
@Composable
fun rememberAiLoadingStage(isLoading: Boolean): AiLoadingStage {
    var stage by remember { mutableStateOf(AiLoadingStage.STARTED) }
    LaunchedEffect(isLoading) {
        stage = AiLoadingStage.STARTED
        if (!isLoading) return@LaunchedEffect
        delay(AiLoadingStage.SLOW_AFTER_MILLIS)
        stage = AiLoadingStage.SLOW
        delay(AiLoadingStage.VERY_SLOW_AFTER_MILLIS - AiLoadingStage.SLOW_AFTER_MILLIS)
        stage = AiLoadingStage.VERY_SLOW
    }
    return stage
}

/**
 * AIA-606: an AI request in progress. A status line says what is happening and, as it goes on, that
 * it is still working (announced politely, so screen-reader users hear it too), above [cards]
 * placeholder cards shaped like the answer to come. The whole block is one indeterminate progress
 * indicator labelled [description] for accessibility.
 */
@Composable
fun AiLoadingSkeleton(
    stage: AiLoadingStage,
    description: String,
    modifier: Modifier = Modifier,
    cards: Int = 3,
) {
    val status = stringResource(
        when (stage) {
            AiLoadingStage.STARTED -> R.string.ai_loading_started
            AiLoadingStage.SLOW -> R.string.ai_loading_slow
            AiLoadingStage.VERY_SLOW -> R.string.ai_loading_very_slow
        },
    )
    val pulse by rememberInfiniteTransition(label = "skeleton").animateFloat(
        initialValue = 0.35f,
        targetValue = 0.8f,
        animationSpec = infiniteRepeatable(tween(durationMillis = 800), RepeatMode.Reverse),
        label = "skeleton-alpha",
    )
    Column(
        verticalArrangement = Arrangement.spacedBy(12.dp),
        modifier = modifier
            .fillMaxWidth()
            .semantics {
                contentDescription = description
                progressBarRangeInfo = ProgressBarRangeInfo.Indeterminate
            },
    ) {
        Text(
            text = status,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier
                .testTag(AiStateTestTags.STATUS)
                .semantics { liveRegion = LiveRegionMode.Polite },
        )
        repeat(cards) {
            SkeletonCard(Modifier.alpha(pulse))
        }
    }
}

/** A grey card shaped like a recipe or result card: a picture square and two lines of text. */
@Composable
private fun SkeletonCard(modifier: Modifier) {
    val shade = MaterialTheme.colorScheme.surfaceVariant
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier
            .fillMaxWidth()
            .testTag(AiStateTestTags.SKELETON)
            // Decorative: the block around it is labelled.
            .clearAndSetSemantics {},
    ) {
        Row(
            modifier = modifier.padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Box(Modifier.size(72.dp).background(shade, MaterialTheme.shapes.medium))
            Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
                Box(Modifier.fillMaxWidth(0.7f).height(16.dp).background(shade, MaterialTheme.shapes.small))
                Box(Modifier.fillMaxWidth(0.45f).height(12.dp).background(shade, MaterialTheme.shapes.small))
            }
        }
    }
}

/**
 * AIA-606: an AI request that failed. The [message] is announced (it carries [messageTestTag]),
 * [onRetry] asks again, and when the AI cannot help a clearly labelled non-AI [fallbackLabel] can
 * take the user somewhere useful instead ([onFallback]).
 */
@Composable
fun AiErrorCard(
    message: String,
    onRetry: () -> Unit,
    messageTestTag: String,
    modifier: Modifier = Modifier,
    retryEnabled: Boolean = true,
    fallbackLabel: String? = null,
    onFallback: (() -> Unit)? = null,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
        modifier = modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(
                text = message,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onErrorContainer,
                modifier = Modifier
                    .testTag(messageTestTag)
                    .semantics { liveRegion = LiveRegionMode.Polite },
            )
            Button(
                onClick = onRetry,
                enabled = retryEnabled,
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag(AiStateTestTags.RETRY),
            ) {
                Text(stringResource(R.string.ai_retry))
            }
            if (fallbackLabel != null && onFallback != null) {
                OutlinedButton(
                    onClick = onFallback,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag(AiStateTestTags.FALLBACK),
                ) {
                    Text(fallbackLabel)
                }
            }
        }
    }
}
