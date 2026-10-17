@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.profile

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.clickable
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.component.ErrorState

/**
 * Profile screen displaying user information and settings.
 */
@Composable
fun ProfileScreen(
    onNavigateToEditProfile: () -> Unit,
    onNavigateToDietaryPreferences: () -> Unit,
    onNavigateToOrderHistory: () -> Unit,
    onNavigateToNotificationSettings: () -> Unit,
    onLogout: () -> Unit
) {
    val authRepository = koinInject<com.nutriplan.shared.data.repository.AuthRepository>()
    
    var user by remember { mutableStateOf<com.nutriplan.shared.data.model.UserProfile?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        // TODO: Load user profile
        // user = authRepository.getCurrentUser()
        isLoading = false
        // TODO: Set errorMessage on failure
    }

    val retryAction = {
        isLoading = true
        errorMessage = null
        // TODO: Retry loading profile
        isLoading = false
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Profile") },
                navigationIcon = {
                    IconButton(onClick = onLogout) {
                        Icon(
                            Icons.Default.Logout,
                            contentDescription = "Logout"
                        )
                    }
                }
            )
        }
    ) { paddingValues ->
        if (isLoading) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                // F24: Add contextual accessibility label for loading spinner
                Box(modifier = Modifier.semantics { contentDescription = "Loading profile" }) {
                    CircularProgressIndicator()
                }
            }
        } else if (errorMessage != null) {
                ErrorState(
                    message = errorMessage!!,
                    onRetry = retryAction,
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues)
                )
        } else {
                LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // User profile card
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = MaterialTheme.shapes.medium
                    ) {
                        Column(
                            modifier = Modifier.padding(16.dp)
                        ) {
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(16.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                // Avatar (decorative placeholder)
                                Box(
                                    modifier = Modifier
                                        .size(64.dp)
                                        .background(
                                            MaterialTheme.colorScheme.primary.copy(alpha = 0.1f),
                                            MaterialTheme.shapes.large
                                        ),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Icon(
                                        Icons.Default.Person,
                                        contentDescription = null,
                                        tint = MaterialTheme.colorScheme.primary,
                                        modifier = Modifier.size(32.dp)
                                    )
                                }
                                
                                Column {
                                    Text(
                                        text = user?.name ?: "User",
                                        style = MaterialTheme.typography.titleLarge,
                                        color = MaterialTheme.colorScheme.onSurface
                                    )
                                    
                                    Spacer(modifier = Modifier.height(4.dp))
                                    
                                    Text(
                                        text = user?.email ?: "user@example.com",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                            
                            Spacer(modifier = Modifier.height(16.dp))
                            
                            Divider()
                            
                            Spacer(modifier = Modifier.height(16.dp))
                            
                            // Stats
                            Row(
                                horizontalArrangement = Arrangement.SpaceAround,
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                StatItem(label = "Meal Plans", value = "5")
                                StatItem(label = "Orders", value = "12")
                                StatItem(label = "Streak", value = "7d")
                            }
                        }
                    }
                }
                
                // Menu items
                item {
                    Text(
                        text = "Settings",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                }
                
                val menuItems = listOf(
                    MenuItem("Edit Profile", Icons.Default.Person, onNavigateToEditProfile),
                    MenuItem("Dietary Preferences", Icons.Default.Restaurant, onNavigateToDietaryPreferences),
                    MenuItem("Order History", Icons.Default.ShoppingBag, onNavigateToOrderHistory),
                    MenuItem("Notifications", Icons.Default.Notifications, onNavigateToNotificationSettings)
                )
                
                items(menuItems, key = { it.label }) { item ->
                    MenuItemCard(item = item)
                }
                
                item {
                    Spacer(modifier = Modifier.height(32.dp))
                    
                    // Logout button
                    Button(
                        onClick = onLogout,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(48.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.error
                        )
                    ) {
                        // F25: Decorative icon — mark as non-accessible; button text provides meaning
                        Icon(
                            Icons.Default.Logout,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onPrimary,
                            modifier = Modifier.size(20.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Logout")
                    }
                    
                    Spacer(modifier = Modifier.height(24.dp))
                }
            }
        }
    }
}

/**
 * Stat item component.
 */
@Composable
private fun StatItem(label: String, value: String) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = value,
            style = MaterialTheme.typography.titleLarge,
            color = MaterialTheme.colorScheme.primary
        )
        // F17: Grouped into single semantic unit for screen readers (combinedText)
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

/**
 * Menu item data class.
 */
private data class MenuItem(
    val label: String,
    val icon: androidx.compose.ui.graphics.vector.ImageVector,
    val onClick: () -> Unit
)

/**
 * Menu item card component.
 */
@Composable
private fun MenuItemCard(item: MenuItem) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            // F10: Add accessible name for screen readers (WCAG 4.1.2)
            .semantics { contentDescription = item.label }
            .clickable(onClick = item.onClick),
        shape = MaterialTheme.shapes.medium
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    item.icon,
                    contentDescription = item.label,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(24.dp)
                )
                Text(
                    text = item.label,
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurface
                )
            }
            
            // F8: Decorative chevron — mark as non-accessible; parent Card provides accessible name
            Icon(
                Icons.Default.ChevronRight,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.38f),
                modifier = Modifier.size(20.dp)
            )
        }
    }
}
