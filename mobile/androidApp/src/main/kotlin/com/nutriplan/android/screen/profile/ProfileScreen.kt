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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.nutriplan.android.R
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.di.koinInject
import com.nutriplan.shared.profile.ProfileViewModel
import kotlinx.coroutines.launch

/**
 * Profile screen displaying the signed-in user's information and settings (IDN-606).
 *
 * Reads the shared [ProfileViewModel] so an edit made on the edit/preferences screens is reflected
 * here immediately.
 */
@Composable
fun ProfileScreen(
    onNavigateToEditProfile: () -> Unit,
    onNavigateToDietaryPreferences: () -> Unit,
    onNavigateToOrderHistory: () -> Unit,
    onNavigateToNotificationSettings: () -> Unit,
    onLogout: () -> Unit,
    /** COM-601: the delivery address book. */
    onNavigateToAddresses: () -> Unit = {},
    /** COM-603: the saved payment methods. */
    onNavigateToPaymentMethods: () -> Unit = {},
) {
    val addressesLabel = stringResource(R.string.address_book_title)
    val paymentMethodsLabel = stringResource(R.string.payment_methods_title)
    val viewModel = koinInject<ProfileViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        if (!state.hasProfile) viewModel.load()
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
        when {
            state.isLoading && !state.hasProfile -> {
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
            }

            state.loadError != null && !state.hasProfile -> {
                ErrorState(
                    message = state.loadError.orEmpty(),
                    onRetry = { scope.launch { viewModel.load() } },
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues)
                )
            }

            else -> {
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
                                    ProfileAvatar(avatarUrl = state.profile?.avatarUrl)

                                    Column {
                                        Text(
                                            text = state.profile?.name ?: "User",
                                            style = MaterialTheme.typography.titleLarge,
                                            color = MaterialTheme.colorScheme.onSurface
                                        )

                                        Spacer(modifier = Modifier.height(4.dp))

                                        Text(
                                            text = state.profile?.email ?: "",
                                            style = MaterialTheme.typography.bodyMedium,
                                            color = MaterialTheme.colorScheme.onSurface
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
                        MenuItem(addressesLabel, Icons.Default.LocationOn, onNavigateToAddresses),
                        MenuItem(paymentMethodsLabel, Icons.Default.CreditCard, onNavigateToPaymentMethods),
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
}

/**
 * Shows the remote avatar when one is set, falling back to a person icon placeholder.
 */
@Composable
private fun ProfileAvatar(avatarUrl: String?) {
    Box(
        modifier = Modifier
            .size(64.dp)
            .background(
                MaterialTheme.colorScheme.primary.copy(alpha = 0.1f),
                MaterialTheme.shapes.large
            ),
        contentAlignment = Alignment.Center
    ) {
        if (avatarUrl.isNullOrBlank()) {
            Icon(
                Icons.Default.Person,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(32.dp)
            )
        } else {
            AsyncImage(
                model = avatarUrl,
                contentDescription = "Profile photo",
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .fillMaxSize()
                    .clip(MaterialTheme.shapes.large)
            )
        }
    }
}

/**
 * Stat item component.
 *
 * Groups the value and label into a single semantic unit so screen readers announce them
 * together (WCAG 1.3.1, Info and Relationships / F17).
 */
@Composable
private fun StatItem(label: String, value: String) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        // F17: Group value and label into a single semantic unit for screen readers
        modifier = Modifier.semantics { contentDescription = "$value $label" }
    ) {
        Text(
            text = value,
            style = MaterialTheme.typography.titleLarge,
            color = MaterialTheme.colorScheme.primary
        )
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface
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
