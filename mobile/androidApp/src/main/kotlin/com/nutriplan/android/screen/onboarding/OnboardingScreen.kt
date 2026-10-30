package com.nutriplan.android.screen.onboarding

import androidx.compose.foundation.layout.*
import kotlinx.coroutines.launch
import androidx.compose.foundation.background
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.android.component.NutriPlanButton
import com.nutriplan.android.ui.theme.NutriPlanTheme

/**
 * Onboarding screen with multi-step flow.
 */
@Composable
fun OnboardingScreen(
    onGetStarted: () -> Unit
) {
    val pagerState = rememberPagerState(pageCount = { OnboardingPage.entries.size })
    val scope = rememberCoroutineScope()
    val pagesDescription = stringResource(
        R.string.cd_intro_pages,
        pagerState.currentPage + 1,
        pagerState.pageCount,
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.SpaceBetween
    ) {
        // Skip button
        TextButton(
            onClick = onGetStarted,
            modifier = Modifier.align(Alignment.End)
        ) {
            Text(stringResource(R.string.intro_skip))
        }
        
        // Pager content
        HorizontalPager(
            state = pagerState,
            modifier = Modifier
                .weight(1f)
                // F13: Add accessibility role and page count for screen readers (WCAG 1.3.1, 4.1.2)
                .semantics {
                    contentDescription = pagesDescription
                }
        ) { page ->
            OnboardingPage.entries[page].Content()
        }
        
        // Page indicator
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.padding(vertical = 24.dp)
        ) {
            OnboardingPage.entries.forEachIndexed { index, _ ->
                val pageDescription = stringResource(
                    if (index == pagerState.currentPage) R.string.cd_intro_page_current else R.string.cd_intro_page,
                    index + 1,
                    pagerState.pageCount,
                )
                Box(
                    modifier = Modifier
                        .size(if (index == pagerState.currentPage) 8.dp else 6.dp)
                        .clip(CircleShape)
                        .background(
                            if (index == pagerState.currentPage) 
                                MaterialTheme.colorScheme.primary 
                            // F3: Raised from 0.2f to 0.38f for WCAG AA non-text contrast ≥3:1
                            else 
                                MaterialTheme.colorScheme.onSurface.copy(alpha = 0.38f)
                        )
                    // F14: Add accessibility label for page dots (WCAG 4.1.2)
                    .semantics {
                        contentDescription = pageDescription
                    }
                )
            }
        }
        
        // Next/Get Started button
        NutriPlanButton(
            onClick = {
                if (pagerState.currentPage == OnboardingPage.entries.size - 1) {
                    onGetStarted()
                } else {
                    scope.launch { pagerState.animateScrollToPage(pagerState.currentPage + 1) }
                }
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(
                stringResource(
                    if (pagerState.currentPage == OnboardingPage.entries.size - 1) {
                        R.string.intro_get_started
                    } else {
                        R.string.intro_next
                    },
                ),
            )
        }
        
        Spacer(modifier = Modifier.height(24.dp))
    }
}

/**
 * Onboarding page content.
 */
@Composable
private fun OnboardingPage.Content() {
    when (this) {
        OnboardingPage.WELCOME -> WelcomeContent()
        OnboardingPage.MEAL_PLANS -> MealPlansContent()
        OnboardingPage.TRACKING -> TrackingContent()
    }
}

/**
 * Welcome page content.
 */
@Composable
private fun WelcomeContent() {
    val illustrationDescription = stringResource(R.string.cd_intro_welcome_illustration)
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
        modifier = Modifier.fillMaxSize()
    ) {
        // F15: Add content description for emoji; F20: Use defaultMinSize instead of fixed size (WCAG 1.4.4)
        Box(
            modifier = Modifier
                .defaultMinSize(minWidth = 120.dp, minHeight = 120.dp)
                .semantics { contentDescription = illustrationDescription },
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = "🥗",
                textAlign = TextAlign.Center
            )
        }
        
        Spacer(modifier = Modifier.height(32.dp))
        
        Text(
            text = stringResource(R.string.intro_welcome_title),
            style = MaterialTheme.typography.headlineLarge,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = stringResource(R.string.intro_welcome_body),
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface
        )
    }
}

/**
 * Meal plans page content.
 */
@Composable
private fun MealPlansContent() {
    val illustrationDescription = stringResource(R.string.cd_intro_meals_illustration)
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
        modifier = Modifier.fillMaxSize()
    ) {
        // F15: Add content description for emoji; F20: Use defaultMinSize instead of fixed size (WCAG 1.4.4)
        Box(
            modifier = Modifier
                .defaultMinSize(minWidth = 120.dp, minHeight = 120.dp)
                .semantics { contentDescription = illustrationDescription },
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = "📋",
                textAlign = TextAlign.Center
            )
        }
        
        Spacer(modifier = Modifier.height(32.dp))
        
        Text(
            text = stringResource(R.string.intro_meals_title),
            style = MaterialTheme.typography.headlineLarge,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = stringResource(R.string.intro_meals_body),
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface
        )
    }
}

/**
 * Tracking page content.
 */
@Composable
private fun TrackingContent() {
    val illustrationDescription = stringResource(R.string.cd_intro_tracking_illustration)
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
        modifier = Modifier.fillMaxSize()
    ) {
        // F15: Add content description for emoji; F20: Use defaultMinSize instead of fixed size (WCAG 1.4.4)
        Box(
            modifier = Modifier
                .defaultMinSize(minWidth = 120.dp, minHeight = 120.dp)
                .semantics { contentDescription = illustrationDescription },
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = "📊",
                textAlign = TextAlign.Center
            )
        }
        
        Spacer(modifier = Modifier.height(32.dp))
        
        Text(
            text = stringResource(R.string.intro_tracking_title),
            style = MaterialTheme.typography.headlineLarge,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = stringResource(R.string.intro_tracking_body),
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface
        )
    }
}

/**
 * Onboarding pages enum.
 */
private enum class OnboardingPage {
    WELCOME,
    MEAL_PLANS,
    TRACKING;
}
