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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
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
            Text("Skip")
        }
        
        // Pager content
        HorizontalPager(
            state = pagerState,
            modifier = Modifier
                .weight(1f)
                // F13: Add accessibility role and page count for screen readers (WCAG 1.3.1, 4.1.2)
                .semantics {
                    contentDescription = "Onboarding pages, ${pagerState.currentPage + 1} of ${pagerState.pageCount}"
                }
        ) { page ->
            OnboardingPage.entries[page].Content()
        }
        
        // Page indicator
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.padding(vertical = 24.dp)
        ) {
            OnboardingPage.entries.forEachIndexed { index, page ->
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
                        contentDescription = "Page ${index + 1} of ${pagerState.pageCount}${if (index == pagerState.currentPage) ", current" else ""}"
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
                if (pagerState.currentPage == OnboardingPage.entries.size - 1) 
                    "Get Started" 
                else 
                    "Next"
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
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
        modifier = Modifier.fillMaxSize()
    ) {
        // F15: Add content description for emoji; F20: Use defaultMinSize instead of fixed size (WCAG 1.4.4)
        Box(
            modifier = Modifier
                .defaultMinSize(minWidth = 120.dp, minHeight = 120.dp)
                .semantics { contentDescription = "Fresh food illustration" },
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = "🥗",
                textAlign = TextAlign.Center
            )
        }
        
        Spacer(modifier = Modifier.height(32.dp))
        
        Text(
            text = "Welcome to NutriPlan",
            style = MaterialTheme.typography.headlineLarge,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = "Your personal nutrition assistant. Get personalized meal plans, track your progress, and eat healthier.",
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.64f) // WCAG AA: ≥0.54 for normal text (F2)
        )
    }
}

/**
 * Meal plans page content.
 */
@Composable
private fun MealPlansContent() {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
        modifier = Modifier.fillMaxSize()
    ) {
        // F15: Add content description for emoji; F20: Use defaultMinSize instead of fixed size (WCAG 1.4.4)
        Box(
            modifier = Modifier
                .defaultMinSize(minWidth = 120.dp, minHeight = 120.dp)
                .semantics { contentDescription = "Meal plan illustration" },
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = "📋",
                textAlign = TextAlign.Center
            )
        }
        
        Spacer(modifier = Modifier.height(32.dp))
        
        Text(
            text = "Personalized Meal Plans",
            style = MaterialTheme.typography.headlineLarge,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = "Get meal plans tailored to your dietary preferences, health goals, and taste.",
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.64f) // WCAG AA: ≥0.54 for normal text (F2)
        )
    }
}

/**
 * Tracking page content.
 */
@Composable
private fun TrackingContent() {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
        modifier = Modifier.fillMaxSize()
    ) {
        // F15: Add content description for emoji; F20: Use defaultMinSize instead of fixed size (WCAG 1.4.4)
        Box(
            modifier = Modifier
                .defaultMinSize(minWidth = 120.dp, minHeight = 120.dp)
                .semantics { contentDescription = "Progress tracking illustration" },
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = "📊",
                textAlign = TextAlign.Center
            )
        }
        
        Spacer(modifier = Modifier.height(32.dp))
        
        Text(
            text = "Track Your Progress",
            style = MaterialTheme.typography.headlineLarge,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = "Monitor your nutrition intake, track your meals, and achieve your health goals.",
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.64f) // WCAG AA: ≥0.54 for normal text (F2)
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
