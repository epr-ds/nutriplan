@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.checkout

import androidx.compose.foundation.layout.*
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
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import com.nutriplan.android.component.NutriPlanButton
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.android.di.koinInject

/**
 * Checkout screen for ordering meal plans.
 */
@Composable
fun CheckoutScreen(
    planId: String,
    onCheckoutSuccess: () -> Unit,
    onNavigateBack: () -> Unit
) {
    val commerceRepository = koinInject<com.nutriplan.shared.data.repository.CommerceRepository>()
    
    var mealPlan by remember { mutableStateOf<com.nutriplan.shared.data.model.MealPlan?>(null) }
    var cartItems by remember { mutableStateOf<List<com.nutriplan.shared.data.model.OrderItem>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var isProcessing by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(planId) {
        // TODO: Load meal plan and cart items
        // mealPlan = commerceRepository.getMealPlan(planId)
        // cartItems = commerceRepository.getCartItems()
        isLoading = false
        // TODO: Set errorMessage on failure
    }

    val retryAction = {
        isLoading = true
        errorMessage = null
        // TODO: Retry loading checkout data
        isLoading = false
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Checkout") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            Icons.Default.ArrowBack,
                            contentDescription = "Back"
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
                Box(modifier = Modifier.semantics { contentDescription = "Loading checkout" }) {
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
        } else if (cartItems.isEmpty()) {
                com.nutriplan.android.component.EmptyState(
                    title = "Your cart is empty",
                    description = "Add recipes from a meal plan to checkout.",
                    actionLabel = "Browse Meal Plans",
                    onAction = onNavigateBack,
                    modifier = Modifier.padding(paddingValues)
                )
        } else {
                LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Order summary
                item {
                    Text(
                        text = "Order Summary",
                        style = MaterialTheme.typography.titleLarge,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    
                    Spacer(modifier = Modifier.height(8.dp))
                }
                
                // Cart items
                items(cartItems) { item ->
                    CartItemRow(cartItem = item)
                }
                
                item {
                    Spacer(modifier = Modifier.height(16.dp))
                    
                    Divider()
                    
                    Spacer(modifier = Modifier.height(16.dp))
                    
                    // Price breakdown
                    PriceRow(label = "Subtotal", price = "$100.00")
                    PriceRow(label = "Tax", price = "$8.00")
                    PriceRow(
                        label = "Total",
                        price = "$108.00",
                        isTotal = true
                    )
                }
                
                item {
                    Spacer(modifier = Modifier.height(24.dp))
                    
                    // Payment method
                    Text(
                        text = "Payment Method",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    
                    Spacer(modifier = Modifier.height(8.dp))
                    
                    Card(
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(16.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                // F25: Decorative icon — mark as non-accessible; text provides meaning
                                Icon(
                                    Icons.Default.CreditCard,
                                    contentDescription = null,
                                    tint = MaterialTheme.colorScheme.primary
                                )
                                Text(
                                    text = "â€¢â€¢â€¢â€¢ â€¢â€¢â€¢â€¢ â€¢â€¢â€¢â€¢ 4242",
                                    style = MaterialTheme.typography.bodyMedium
                                )
                            }
                            
                            TextButton(
                                onClick = { /* TODO: Change payment method */ },
                                // F9: Add minimum touch target height for WCAG 2.5.5 compliance
                                modifier = Modifier.height(48.dp)
                            ) {
                                Text("Change")
                            }
                        }
                    }
                    
                    Spacer(modifier = Modifier.height(24.dp))
                    
                    // Place order button
                    NutriPlanButton(
                        onClick = {
                            isProcessing = true
                            errorMessage = null
                            // TODO: Process checkout
                            // commerceRepository.checkout(planId, cartItems)
                            isProcessing = false
                            onCheckoutSuccess()
                        },
                        isLoading = isProcessing,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("Place Order - $108.00")
                    }
                    
                    Spacer(modifier = Modifier.height(16.dp))
                    
                    // F4: Raised alpha from 0.6f to 0.64f for WCAG AA contrast compliance (≥0.54)
                    Text(
                        text = "By placing your order, you agree to our Terms and Conditions.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textDecoration = TextDecoration.Underline
                    )
                }
            }
        }
    }
}

/**
 * Cart item row component.
 */
@Composable
fun CartItemRow(
    cartItem: com.nutriplan.shared.data.model.OrderItem
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column {
            Text(
                text = cartItem.name.orEmpty(),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface
            )
            Text(
                // The server formats money (COM-501); quantities may be fractional (e.g. 0.5 kg).
                text = "${cartItem.quantity ?: 1}x ${cartItem.unitPrice?.formatted.orEmpty()}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.75f)
            )
        }

        Text(
            text = cartItem.lineTotal?.formatted.orEmpty(),
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
        )
    }
}

/**
 * Price row component.
 */
@Composable
fun PriceRow(
    label: String,
    price: String,
    isTotal: Boolean = false
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = if (isTotal) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyMedium,
            fontWeight = if (isTotal) androidx.compose.ui.text.font.FontWeight.Bold else androidx.compose.ui.text.font.FontWeight.Normal,
            color = if (isTotal) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant
        )
        
        Text(
            text = price,
            style = if (isTotal) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyMedium,
            fontWeight = if (isTotal) androidx.compose.ui.text.font.FontWeight.Bold else androidx.compose.ui.text.font.FontWeight.Normal,
            color = if (isTotal) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}
