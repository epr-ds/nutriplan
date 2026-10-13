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
            modifier = Modifier.weight(1f)
        ) { page ->
            OnboardingPage.entries[page].Content()
        }
        
        // Page indicator
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.padding(vertical = 24.dp)
        ) {
            OnboardingPage.entries.forEachIndexed { index, _ ->
                Box(
                    modifier = Modifier
                        .size(if (index == pagerState.currentPage) 8.dp else 6.dp)
                        .clip(CircleShape)
                        .background(
                            if (index == pagerState.currentPage) 
                                MaterialTheme.colorScheme.primary 
                            else 
                                MaterialTheme.colorScheme.onSurface.copy(alpha = 0.2f)
                        )
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
        Text(
            text = "ðŸ¥—",
            modifier = Modifier.size(120.dp),
            textAlign = TextAlign.Center
        )
        
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
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
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
        Text(
            text = "ðŸ“‹",
            modifier = Modifier.size(120.dp),
            textAlign = TextAlign.Center
        )
        
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
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
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
        Text(
            text = "ðŸ“Š",
            modifier = Modifier.size(120.dp),
            textAlign = TextAlign.Center
        )
        
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
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
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
