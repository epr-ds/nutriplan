package com.nutriplan.android.screen.profile

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.nutriplan.shared.ui.theme.NutriPlanTheme
import org.koin.androidx.compose.koinInject

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
    val authRepository = koinInject<com.nutriplan.shared.repository.AuthRepository>()
    
    var user by remember { mutableStateOf<com.nutriplan.shared.model.User?>(null) }
    var isLoading by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) {
        // TODO: Load user profile
        // user = authRepository.getCurrentUser()
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
                CircularProgressIndicator()
            }
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
                                // Avatar
                                Box(
                                    modifier = Modifier
                                        .size(64.dp)
                                        .background(
                                            NutriPlanTheme.colors.primary.copy(alpha = 0.1f),
                                            MaterialTheme.shapes.large
                                        ),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Icon(
                                        Icons.Default.Person,
                                        contentDescription = "Avatar",
                                        tint = NutriPlanTheme.colors.primary,
                                        modifier = Modifier.size(32.dp)
                                    )
                                }
                                
                                Column {
                                    Text(
                                        text = user?.name ?: "User",
                                        style = MaterialTheme.typography.titleLarge,
                                        color = NutriPlanTheme.colors.onSurface
                                    )
                                    
                                    Spacer(modifier = Modifier.height(4.dp))
                                    
                                    Text(
                                        text = user?.email ?: "user@example.com",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
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
                        color = NutriPlanTheme.colors.onSurface
                    )
                }
                
                val menuItems = listOf(
                    MenuItem("Edit Profile", Icons.Default.Person, onNavigateToEditProfile),
                    MenuItem("Dietary Preferences", Icons.Default.Restaurant, onNavigateToDietaryPreferences),
                    MenuItem("Order History", Icons.Default.ShoppingBag, onNavigateToOrderHistory),
                    MenuItem("Notifications", Icons.Default.Notifications, onNavigateToNotificationSettings)
                )
                
                items(menuItems, key = { it.id }) { item ->
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
                        Icon(
                            Icons.Default.Logout,
                            contentDescription = null,
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
            color = NutriPlanTheme.colors.primary
        )
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
        )
    }
}

/**
 * Menu item data class.
 */
private data class MenuItem(
    val id: String,
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
                    tint = NutriPlanTheme.colors.primary,
                    modifier = Modifier.size(24.dp)
                )
                Text(
                    text = item.label,
                    style = MaterialTheme.typography.bodyLarge,
                    color = NutriPlanTheme.colors.onSurface
                )
            }
            
            Icon(
                Icons.Default.ChevronRight,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f),
                modifier = Modifier.size(20.dp)
            )
        }
    }
}
